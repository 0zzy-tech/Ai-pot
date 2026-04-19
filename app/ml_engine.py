"""
TinyML Engine — 4 lightweight on-device models using scikit-learn.

All models run in-process on the same Raspberry Pi Docker image.
Training is done in a thread executor so it never blocks the async event loop.
Models are persisted to /data/ml_models/ and reloaded on restart.

Models:
  1. Isolation Forest    — anomaly detection (unusual requests)
  2. DBSCAN              — attack clustering (coordinated campaigns)
  3. Random Forest       — risk score enhancement (continuous probability)
  4. Random Forest       — bot detection (automated vs human session)

Cold-start safe: all score methods return None until first training completes.
Training triggers when 100+ requests exist, then every 200 new samples or 60 min.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
MIN_SAMPLES_TO_TRAIN  = 100    # Minimum requests before first training
RETRAIN_EVERY_N       = 200    # Retrain after this many new samples
RETRAIN_EVERY_SECS    = 3600   # Retrain at least every 60 minutes
ANOMALY_THRESHOLD     = 0.65   # Isolation Forest score above which = anomalous
MODEL_DIR             = Path(os.getenv("MODEL_DIR", "/data/ml_models"))

CATEGORY_MAP = {
    "inference": 0, "openai_compat": 1, "anthropic": 2, "model_management": 3,
    "embeddings": 4, "rerank": 5, "image_generation": 6, "audio_transcription": 7,
    "code_completion": 8, "model_info": 9, "enumeration": 10,
    "scanning": 11, "attack": 12,
}
RISK_MAP = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


class MLEngine:
    def __init__(self):
        self._iso_forest       = None   # IsolationForest
        self._risk_clf         = None   # RandomForestClassifier
        self._bot_clf          = None   # RandomForestClassifier
        self._cluster_registry: dict[str, int] = {}  # ip → cluster_id
        self._trained          = False
        self._samples_at_last_train = 0
        self._last_train_time: datetime | None = None
        self._training_lock    = asyncio.Lock()
        self._total_samples    = 0

    # ── Startup ───────────────────────────────────────────────────────────────

    def load(self) -> None:
        """Load persisted models from disk. Safe to call even if files don't exist."""
        try:
            import joblib
            MODEL_DIR.mkdir(parents=True, exist_ok=True)

            iso_path     = MODEL_DIR / "isolation_forest.joblib"
            risk_path    = MODEL_DIR / "risk_clf.joblib"
            bot_path     = MODEL_DIR / "bot_clf.joblib"
            cluster_path = MODEL_DIR / "cluster_registry.joblib"

            if iso_path.exists():
                self._iso_forest = joblib.load(iso_path)
            if risk_path.exists():
                self._risk_clf = joblib.load(risk_path)
            if bot_path.exists():
                self._bot_clf = joblib.load(bot_path)
            if cluster_path.exists():
                self._cluster_registry = joblib.load(cluster_path)

            if self._iso_forest is not None:
                self._trained = True
                logger.info("ML engine: models loaded from %s", MODEL_DIR)
            else:
                logger.info("ML engine: cold start — waiting for %d requests", MIN_SAMPLES_TO_TRAIN)
        except Exception as exc:
            logger.warning("ML engine: failed to load models: %s", exc)

    def _save(self) -> None:
        """Persist all models to disk. Called from training thread."""
        try:
            import joblib
            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            if self._iso_forest:
                joblib.dump(self._iso_forest,    MODEL_DIR / "isolation_forest.joblib")
            if self._risk_clf:
                joblib.dump(self._risk_clf,      MODEL_DIR / "risk_clf.joblib")
            if self._bot_clf:
                joblib.dump(self._bot_clf,       MODEL_DIR / "bot_clf.joblib")
            joblib.dump(self._cluster_registry,  MODEL_DIR / "cluster_registry.joblib")
        except Exception as exc:
            logger.warning("ML engine: failed to save models: %s", exc)

    # ── Background training loop ──────────────────────────────────────────────

    async def training_loop(self) -> None:
        """Asyncio background task — trains periodically without blocking."""
        while True:
            await asyncio.sleep(60)  # Check every minute
            await self._maybe_train()

    async def _maybe_train(self) -> None:
        """Trigger training if enough new data or time has elapsed."""
        if self._training_lock.locked():
            return  # Already training

        from app.database import get_db
        async with get_db() as db:
            cur = await db.execute("SELECT COUNT(*) FROM requests")
            total = (await cur.fetchone())[0]

        self._total_samples = total
        if total < MIN_SAMPLES_TO_TRAIN:
            return

        new_samples = total - self._samples_at_last_train
        elapsed_secs = (
            (datetime.now(timezone.utc) - self._last_train_time).total_seconds()
            if self._last_train_time else RETRAIN_EVERY_SECS + 1
        )

        if new_samples >= RETRAIN_EVERY_N or elapsed_secs >= RETRAIN_EVERY_SECS:
            async with self._training_lock:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._train_sync, total)

    def _train_sync(self, total_samples: int) -> None:
        """
        Blocking training — runs in a thread executor.
        Fetches data from SQLite synchronously using the stdlib sqlite3.
        """
        try:
            import sqlite3
            import numpy as np
            from sklearn.ensemble import IsolationForest, RandomForestClassifier
            from sklearn.cluster import DBSCAN
            from sklearn.preprocessing import StandardScaler

            db_path = os.getenv("DB_PATH", "honeypot.db")
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row

            # ── Fetch request training data ───────────────────────────────────
            rows = conn.execute("""
                SELECT timestamp, method, path, body, headers, category,
                       risk_level, flagged_patterns, is_c2
                FROM requests
                ORDER BY id DESC
                LIMIT 5000
            """).fetchall()

            if len(rows) < MIN_SAMPLES_TO_TRAIN:
                conn.close()
                return

            # ── Build per-request feature matrix ─────────────────────────────
            X_req, y_risk = [], []
            for r in rows:
                feats = self._request_features_from_row(r)
                X_req.append(feats)
                y_risk.append(RISK_MAP.get(r["risk_level"], 0))

            X_req = np.array(X_req, dtype=float)

            # ── 1. Isolation Forest (anomaly) ─────────────────────────────────
            iso = IsolationForest(
                n_estimators=50,
                contamination=0.1,
                random_state=42,
                n_jobs=1,       # single thread — Pi friendly
            )
            iso.fit(X_req)
            self._iso_forest = iso

            # ── 2. Risk classifier ────────────────────────────────────────────
            if len(set(y_risk)) > 1:  # Need at least 2 classes
                rf_risk = RandomForestClassifier(
                    n_estimators=30,
                    max_depth=6,
                    random_state=42,
                    n_jobs=1,
                )
                rf_risk.fit(X_req, y_risk)
                self._risk_clf = rf_risk

            # ── Fetch per-IP session data for clustering + bot detection ──────
            ip_rows = conn.execute("""
                SELECT ip,
                       COUNT(*) as cnt,
                       COUNT(DISTINCT path) as unique_paths,
                       COUNT(DISTINCT user_agent) as unique_uas,
                       MIN(timestamp) as first_seen,
                       MAX(timestamp) as last_seen,
                       AVG(CASE WHEN risk_level IN ('HIGH','CRITICAL') THEN 1.0 ELSE 0.0 END) as high_ratio,
                       AVG(CASE WHEN risk_level = 'CRITICAL' THEN 1.0 ELSE 0.0 END) as crit_ratio,
                       COUNT(DISTINCT category) as unique_cats,
                       AVG(CASE WHEN body IS NOT NULL THEN LENGTH(body) ELSE 0 END) as avg_body
                FROM requests
                GROUP BY ip
                HAVING cnt >= 2
            """).fetchall()
            conn.close()

            if len(ip_rows) >= 5:
                X_session, ips, y_bot = [], [], []
                for r in ip_rows:
                    feats = self._session_features_from_row(r)
                    X_session.append(feats)
                    ips.append(r["ip"])
                    # Heuristic bot label: low unique paths + high request count
                    path_ratio = r["unique_paths"] / max(r["cnt"], 1)
                    y_bot.append(1 if (r["cnt"] > 5 and path_ratio < 0.3) else 0)

                X_session = np.array(X_session, dtype=float)

                # ── 3. DBSCAN clustering ──────────────────────────────────────
                scaler = StandardScaler()
                X_scaled = scaler.fit_transform(X_session)
                db = DBSCAN(eps=1.2, min_samples=2, n_jobs=1)
                labels = db.fit_predict(X_scaled)
                self._cluster_registry = {ip: int(lbl) for ip, lbl in zip(ips, labels)}

                # ── 4. Bot classifier ─────────────────────────────────────────
                if sum(y_bot) > 0 and sum(y_bot) < len(y_bot):
                    rf_bot = RandomForestClassifier(
                        n_estimators=20,
                        max_depth=4,
                        random_state=42,
                        n_jobs=1,
                    )
                    rf_bot.fit(X_session, y_bot)
                    self._bot_clf = rf_bot

            self._trained = True
            self._samples_at_last_train = total_samples
            self._last_train_time = datetime.now(timezone.utc)
            self._save()
            logger.info("ML engine: trained on %d requests, %d IPs", len(rows), len(ip_rows) if 'ip_rows' in dir() else 0)

        except Exception as exc:
            logger.error("ML engine: training failed: %s", exc, exc_info=True)

    # ── Feature extraction ────────────────────────────────────────────────────

    def _request_features_from_row(self, row) -> list:
        """Extract numeric features from a sqlite3.Row request record."""
        import json
        try:
            body = row["body"] or ""
            path = row["path"] or ""
            headers = json.loads(row["headers"]) if row["headers"] else {}
            patterns = json.loads(row["flagged_patterns"] or "[]")
            hour = 0
            try:
                hour = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")).hour
            except Exception:
                pass
            return [
                min(len(body), 10000),                             # body_len (capped)
                min(len(path), 500),                               # path_len
                path.count("/"),                                   # path_depth
                len(headers),                                      # header_count
                hour,                                              # hour_of_day
                1 if row["method"] == "POST" else 0,               # method_is_post
                1 if body.strip().startswith("{") else 0,          # body_is_json
                1 if "authorization" in headers else 0,            # has_auth_header
                len(patterns),                                     # flagged_count
                CATEGORY_MAP.get(row["category"], 12),             # category_encoded
                1 if row["is_c2"] else 0,                          # is_c2
            ]
        except Exception:
            return [0] * 11

    def _request_features_from_dict(self, req: dict) -> list:
        """Extract numeric features from a runtime request dict."""
        import json
        path    = req.get("path", "")
        body    = req.get("body_text", "") or ""
        headers = req.get("headers", {})
        return [
            min(req.get("body_len", len(body)), 10000),
            min(len(path), 500),
            path.count("/"),
            len(headers),
            req.get("hour_of_day", datetime.now(timezone.utc).hour),
            1 if req.get("method") == "POST" else 0,
            1 if body.strip().startswith("{") else 0,
            1 if "authorization" in headers else 0,
            req.get("flagged_count", 0),
            CATEGORY_MAP.get(req.get("category", ""), 12),
            1 if req.get("is_c2") else 0,
        ]

    def _session_features_from_row(self, row) -> list:
        """Extract numeric session features from an aggregated ip_row."""
        try:
            from datetime import datetime as dt
            time_span = 1.0
            try:
                first = dt.fromisoformat(row["first_seen"].replace("Z", "+00:00"))
                last  = dt.fromisoformat(row["last_seen"].replace("Z", "+00:00"))
                time_span = max((last - first).total_seconds(), 1.0)
            except Exception:
                pass
            cnt = max(row["cnt"], 1)
            return [
                min(cnt, 5000),                                    # total_requests
                min(row["unique_paths"], 500),                     # unique_paths
                min(row["unique_uas"], 20),                        # unique_user_agents
                min(time_span / cnt, 3600),                        # avg_inter_request_secs
                min(time_span, 86400),                             # time_span_seconds
                float(row["high_ratio"] or 0),                     # high_risk_ratio
                float(row["crit_ratio"] or 0),                     # critical_ratio
                min(row["unique_cats"], 13),                       # unique_categories
                float(row["unique_paths"]) / cnt,                  # path_diversity_ratio
                min(float(row["avg_body"] or 0), 10000),           # avg_body_size
            ]
        except Exception:
            return [0.0] * 10

    def _session_features_from_dict(self, session: dict) -> list:
        """Extract numeric session features from a runtime session dict."""
        cnt = max(session.get("total_requests", 1), 1)
        time_span = max(session.get("time_span_seconds", 1.0), 1.0)
        return [
            min(cnt, 5000),
            min(session.get("unique_paths", 1), 500),
            min(session.get("unique_user_agents", 1), 20),
            min(time_span / cnt, 3600),
            min(time_span, 86400),
            float(session.get("high_risk_ratio", 0)),
            float(session.get("critical_ratio", 0)),
            min(session.get("unique_categories", 1), 13),
            float(session.get("unique_paths", 1)) / cnt,
            min(float(session.get("avg_body_size", 0)), 10000),
        ]

    # ── Inference ─────────────────────────────────────────────────────────────

    def score_request(self, req: dict) -> dict:
        """
        Synchronous per-request scoring. Returns empty dict before first training.
        req keys: body_len, path, method, headers, flagged_count, is_c2,
                  is_tor, abuse_score, is_hosting, category, hour_of_day
        """
        if not self._trained:
            return {}

        try:
            import numpy as np
            feats = np.array([self._request_features_from_dict(req)], dtype=float)

            result = {}

            # Anomaly score: decision_function returns negative = anomalous
            if self._iso_forest:
                raw = self._iso_forest.decision_function(feats)[0]
                # Normalise to 0–1 where 1 = most anomalous
                score = float(1.0 - (raw + 0.5))
                result["anomaly_score"] = round(max(0.0, min(1.0, score)), 3)

            # Risk probability (HIGH or CRITICAL)
            if self._risk_clf:
                proba = self._risk_clf.predict_proba(feats)[0]
                # Sum probabilities for HIGH (idx 2) and CRITICAL (idx 3)
                n_classes = len(proba)
                high_prob = sum(proba[i] for i in range(n_classes) if i >= 2)
                result["risk_score"] = round(float(high_prob), 3)

            return result
        except Exception as exc:
            logger.debug("ML score_request failed: %s", exc)
            return {}

    async def score_session_async(self, ip: str) -> dict:
        """
        Async per-IP session scoring. Returns empty dict before first training.
        Fetches session aggregate from DB then scores.
        """
        if not self._trained:
            return {"cluster_id": self._cluster_registry.get(ip)}

        try:
            from app.database import get_db
            import numpy as np
            from datetime import datetime as dt

            async with get_db() as db:
                cur = await db.execute("""
                    SELECT COUNT(*) as cnt,
                           COUNT(DISTINCT path) as unique_paths,
                           COUNT(DISTINCT user_agent) as unique_uas,
                           MIN(timestamp) as first_seen,
                           MAX(timestamp) as last_seen,
                           AVG(CASE WHEN risk_level IN ('HIGH','CRITICAL') THEN 1.0 ELSE 0.0 END) as high_ratio,
                           AVG(CASE WHEN risk_level = 'CRITICAL' THEN 1.0 ELSE 0.0 END) as crit_ratio,
                           COUNT(DISTINCT category) as unique_cats,
                           AVG(CASE WHEN body IS NOT NULL THEN LENGTH(body) ELSE 0 END) as avg_body
                    FROM requests WHERE ip = ?
                """, (ip,))
                row = await cur.fetchone()

            if not row or row["cnt"] < 1:
                return {"cluster_id": self._cluster_registry.get(ip)}

            time_span = 1.0
            try:
                first = dt.fromisoformat(row["first_seen"].replace("Z", "+00:00"))
                last  = dt.fromisoformat(row["last_seen"].replace("Z", "+00:00"))
                time_span = max((last - first).total_seconds(), 1.0)
            except Exception:
                pass

            session = {
                "total_requests":      row["cnt"],
                "unique_paths":        row["unique_paths"],
                "unique_user_agents":  row["unique_uas"],
                "time_span_seconds":   time_span,
                "high_risk_ratio":     float(row["high_ratio"] or 0),
                "critical_ratio":      float(row["crit_ratio"] or 0),
                "unique_categories":   row["unique_cats"],
                "avg_body_size":       float(row["avg_body"] or 0),
            }

            feats = np.array([self._session_features_from_dict(session)], dtype=float)
            result = {"cluster_id": self._cluster_registry.get(ip)}

            if self._bot_clf:
                proba = self._bot_clf.predict_proba(feats)[0]
                # Index 1 = probability of being a bot
                bot_classes = list(self._bot_clf.classes_)
                if 1 in bot_classes:
                    bot_prob = proba[bot_classes.index(1)]
                    result["bot_probability"] = round(float(bot_prob), 3)

            return result

        except Exception as exc:
            logger.debug("ML score_session failed for %s: %s", ip, exc)
            return {"cluster_id": self._cluster_registry.get(ip)}

    # ── Stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Summary stats for the /api/ml/stats endpoint."""
        cluster_counts: dict[int, int] = {}
        for cid in self._cluster_registry.values():
            cluster_counts[cid] = cluster_counts.get(cid, 0) + 1

        return {
            "trained":            self._trained,
            "total_samples":      self._total_samples,
            "min_to_train":       MIN_SAMPLES_TO_TRAIN,
            "samples_at_last_train": self._samples_at_last_train,
            "last_trained":       self._last_train_time.isoformat() if self._last_train_time else None,
            "models": {
                "anomaly_detection": self._iso_forest is not None,
                "risk_enhancement":  self._risk_clf   is not None,
                "bot_detection":     self._bot_clf     is not None,
                "clustering":        bool(self._cluster_registry),
            },
            "cluster_summary": {
                "total_ips_clustered": len(self._cluster_registry),
                "cluster_counts":      {str(k): v for k, v in cluster_counts.items()},
                "noise_count":         cluster_counts.get(-1, 0),
            },
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
engine = MLEngine()
