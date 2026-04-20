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
  5. GeoRisk dict model  — Bayesian country/ASN risk intelligence

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

# Expected feature vector dimensions (bumped by Phase 2 enrichment)
REQUEST_FEATURE_DIM = 15   # was 11 before Phase 2
SESSION_FEATURE_DIM = 15   # was 10 before Phase 2

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

        # Feature 1 — real-time placeholder counters
        self._anomalies_24h    = 0
        self._bots_detected    = 0

        # Feature 4 — GeoRisk dict models (Bayesian smoothed)
        self._country_risk: dict[str, float] = {}
        self._asn_risk:     dict[str, float] = {}

        # Feature 5 — composite score percentiles
        self._composite_p10 = 0.0
        self._composite_p50 = 0.0
        self._composite_p90 = 0.0

    # ── Startup ───────────────────────────────────────────────────────────────

    def load(self) -> None:
        """Load persisted models from disk. Safe to call even if files don't exist."""
        try:
            import joblib
            MODEL_DIR.mkdir(parents=True, exist_ok=True)

            iso_path      = MODEL_DIR / "isolation_forest.joblib"
            risk_path     = MODEL_DIR / "risk_clf.joblib"
            bot_path      = MODEL_DIR / "bot_clf.joblib"
            cluster_path  = MODEL_DIR / "cluster_registry.joblib"
            geo_path      = MODEL_DIR / "geo_risk.joblib"

            if iso_path.exists():
                self._iso_forest = joblib.load(iso_path)
            if risk_path.exists():
                self._risk_clf = joblib.load(risk_path)
            if bot_path.exists():
                self._bot_clf = joblib.load(bot_path)
            if cluster_path.exists():
                self._cluster_registry = joblib.load(cluster_path)
            if geo_path.exists():
                geo_data = joblib.load(geo_path)
                self._country_risk = geo_data.get("country_risk", {})
                self._asn_risk     = geo_data.get("asn_risk", {})

            # Version guard — discard models with wrong feature dimensions
            if self._iso_forest is not None:
                if getattr(self._iso_forest, "n_features_in_", 0) != REQUEST_FEATURE_DIM:
                    logger.warning(
                        "ML engine: model dim mismatch (expected %d, got %d) — forcing retrain",
                        REQUEST_FEATURE_DIM,
                        getattr(self._iso_forest, "n_features_in_", 0),
                    )
                    self._iso_forest = None
                    self._risk_clf   = None
                    self._bot_clf    = None
                    self._trained    = False
                else:
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
            joblib.dump(
                {"country_risk": self._country_risk, "asn_risk": self._asn_risk},
                MODEL_DIR / "geo_risk.joblib",
            )
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
            import statistics
            import numpy as np
            from collections import defaultdict
            from sklearn.ensemble import IsolationForest, RandomForestClassifier
            from sklearn.cluster import DBSCAN
            from sklearn.preprocessing import StandardScaler

            db_path = os.getenv("DB_PATH", "honeypot.db")
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row

            # ── Feature 2: Fetch request training data with ip_cache enrichment ─
            rows = conn.execute("""
                SELECT r.timestamp, r.method, r.path, r.body, r.headers,
                       r.category, r.risk_level, r.flagged_patterns, r.is_c2,
                       r.country, r.asn,
                       COALESCE(c.abuse_score, 0)                              AS abuse_score,
                       COALESCE(c.is_tor, 0)                                   AS is_tor,
                       COALESCE(c.hosting, 0)                                  AS is_hosting,
                       CASE WHEN c.threatfox_hit IS NOT NULL THEN 1 ELSE 0 END AS threatfox_flag
                FROM requests r
                LEFT JOIN ip_cache c ON r.ip = c.ip
                ORDER BY r.id DESC
                LIMIT 5000
            """).fetchall()

            if len(rows) < MIN_SAMPLES_TO_TRAIN:
                conn.close()
                return

            # ── Build per-request feature matrix ─────────────────────────────
            X_req, y_risk = [], []
            now_utc = datetime.now(timezone.utc)
            cutoff_24h = now_utc.timestamp() - 86400

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

            # Feature 1 — count real anomalies in last 24h from training data
            anomalies_24h = 0
            try:
                raw_scores = iso.decision_function(X_req)
                norm_scores = 1.0 - (raw_scores + 0.5)
                norm_scores = np.clip(norm_scores, 0.0, 1.0)
                for i, r in enumerate(rows):
                    ts_val = 0.0
                    try:
                        ts_val = datetime.fromisoformat(
                            r["timestamp"].replace("Z", "+00:00")
                        ).timestamp()
                    except Exception:
                        pass
                    if ts_val >= cutoff_24h and norm_scores[i] >= ANOMALY_THRESHOLD:
                        anomalies_24h += 1
                self._anomalies_24h = anomalies_24h
            except Exception:
                self._anomalies_24h = 0

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

            # ── Feature 4 — Build GeoRisk country/ASN dicts ───────────────────
            country_totals: dict = defaultdict(lambda: [0, 0])  # [total, high+critical]
            asn_totals:     dict = defaultdict(lambda: [0, 0])
            for r in rows:
                risk_val = RISK_MAP.get(r["risk_level"], 0)
                high_flag = 1 if risk_val >= 2 else 0
                ctry = r["country"] or "?"
                asn  = r["asn"]     or "?"
                country_totals[ctry][0] += 1
                country_totals[ctry][1] += high_flag
                asn_totals[asn][0]      += 1
                asn_totals[asn][1]      += high_flag

            # Bayesian smoothed score (add-1 prior)
            self._country_risk = {
                c: round((v[1] + 1) / (v[0] + 2), 4)
                for c, v in country_totals.items()
            }
            self._asn_risk = {
                a: round((v[1] + 1) / (v[0] + 2), 4)
                for a, v in asn_totals.items()
            }

            # ── Feature 3: Timing std dev per IP ──────────────────────────────
            timing_rows = conn.execute("""
                SELECT ip, GROUP_CONCAT(timestamp) AS ts_list
                FROM requests
                GROUP BY ip
                HAVING COUNT(*) >= 3
            """).fetchall()

            timing_std: dict[str, float] = {}
            for tr in timing_rows:
                try:
                    ts_strs = tr["ts_list"].split(",")
                    timestamps = sorted([
                        datetime.fromisoformat(t.strip().replace("Z", "+00:00")).timestamp()
                        for t in ts_strs
                    ])
                    gaps = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
                    if len(gaps) >= 2:
                        std = statistics.stdev(gaps)
                        timing_std[tr["ip"]] = min(std, 3600) / 3600
                    else:
                        timing_std[tr["ip"]] = 0.5  # single gap — default neutral
                except Exception:
                    pass

            # ── Feature 2+3: Fetch per-IP session data (with ip_cache join) ───
            ip_rows = conn.execute("""
                SELECT r.ip,
                       COUNT(*)                                                         AS cnt,
                       COUNT(DISTINCT r.path)                                           AS unique_paths,
                       COUNT(DISTINCT r.user_agent)                                     AS unique_uas,
                       MIN(r.timestamp)                                                 AS first_seen,
                       MAX(r.timestamp)                                                 AS last_seen,
                       AVG(CASE WHEN r.risk_level IN ('HIGH','CRITICAL') THEN 1.0 ELSE 0.0 END) AS high_ratio,
                       AVG(CASE WHEN r.risk_level = 'CRITICAL' THEN 1.0 ELSE 0.0 END)  AS crit_ratio,
                       COUNT(DISTINCT r.category)                                       AS unique_cats,
                       AVG(CASE WHEN r.body IS NOT NULL THEN LENGTH(r.body) ELSE 0 END) AS avg_body,
                       COALESCE(c.abuse_score, 0)                                       AS abuse_score,
                       COALESCE(c.is_tor, 0)                                            AS is_tor,
                       COALESCE(c.hosting, 0)                                           AS is_hosting,
                       CASE WHEN c.threatfox_hit IS NOT NULL THEN 1 ELSE 0 END          AS threatfox_flag
                FROM requests r
                LEFT JOIN ip_cache c ON r.ip = c.ip
                GROUP BY r.ip
                HAVING cnt >= 2
            """).fetchall()
            conn.close()

            if len(ip_rows) >= 5:
                X_session, ips, y_bot = [], [], []
                for r in ip_rows:
                    ip_str = r["ip"]
                    feats = self._session_features_from_row(r, timing_std.get(ip_str, 0.5))
                    X_session.append(feats)
                    ips.append(ip_str)
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

                    # Feature 1 — count real bots detected (bot prob >= 0.8)
                    try:
                        bot_probas = rf_bot.predict_proba(X_session)
                        bot_classes = list(rf_bot.classes_)
                        if 1 in bot_classes:
                            idx1 = bot_classes.index(1)
                            self._bots_detected = int(np.sum(bot_probas[:, idx1] >= 0.8))
                    except Exception:
                        self._bots_detected = 0

            # ── Feature 5 — Composite score percentiles ───────────────────────
            try:
                composites = []
                geo_w, anom_w, risk_w = 0.20, 0.25, 0.35
                raw_scores = self._iso_forest.decision_function(X_req)
                norm_anom  = np.clip(1.0 - (raw_scores + 0.5), 0.0, 1.0)
                if self._risk_clf:
                    risk_probas = self._risk_clf.predict_proba(X_req)
                    n_cls = risk_probas.shape[1]
                    risk_scores = np.array([sum(p[i] for i in range(n_cls) if i >= 2) for p in risk_probas])
                else:
                    risk_scores = np.zeros(len(X_req))

                for i, r in enumerate(rows):
                    geo = self.score_geo(r["country"], r["asn"]) or 0.5
                    c = anom_w * norm_anom[i] + risk_w * risk_scores[i] + geo_w * geo
                    composites.append(float(c))

                if composites:
                    p10, p50, p90 = np.percentile(composites, [10, 50, 90])
                    self._composite_p10 = round(float(p10), 3)
                    self._composite_p50 = round(float(p50), 3)
                    self._composite_p90 = round(float(p90), 3)
            except Exception:
                pass

            self._trained = True
            self._samples_at_last_train = total_samples
            self._last_train_time = datetime.now(timezone.utc)
            self._save()
            logger.info(
                "ML engine: trained on %d requests, %d IPs, %d anomalies_24h, %d bots",
                len(rows), len(ip_rows) if "ip_rows" in dir() else 0,
                self._anomalies_24h, self._bots_detected,
            )

        except Exception as exc:
            logger.error("ML engine: training failed: %s", exc, exc_info=True)

    # ── Feature extraction ────────────────────────────────────────────────────

    def _request_features_from_row(self, row) -> list:
        """Extract 15 numeric features from a sqlite3.Row request record."""
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
                # Feature 2 — ip_cache enrichment
                min(float(row["abuse_score"] or 0), 100) / 100.0, # abuse_score_norm
                1 if row["is_tor"] else 0,                         # is_tor
                1 if row["is_hosting"] else 0,                     # is_hosting
                1 if row["threatfox_flag"] else 0,                 # threatfox_hit
            ]
        except Exception:
            return [0] * REQUEST_FEATURE_DIM

    def _request_features_from_dict(self, req: dict) -> list:
        """Extract 15 numeric features from a runtime request dict."""
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
            # Feature 2 — ip_cache enrichment
            min(float(req.get("abuse_score") or 0), 100) / 100.0,
            1 if req.get("is_tor") else 0,
            1 if req.get("is_hosting") else 0,
            1 if req.get("threatfox_hit") else 0,
        ]

    def _session_features_from_row(self, row, timing_std_norm: float = 0.5) -> list:
        """Extract 15 numeric session features from an aggregated ip_row."""
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
                # Feature 2 — ip_cache enrichment
                min(float(row["abuse_score"] or 0), 100) / 100.0, # abuse_score_norm
                1 if row["is_tor"] else 0,                         # is_tor
                1 if row["is_hosting"] else 0,                     # is_hosting
                1 if row["threatfox_flag"] else 0,                 # threatfox_hit
                # Feature 3 — timing regularity
                float(timing_std_norm),                            # timing_std_norm
            ]
        except Exception:
            return [0.0] * SESSION_FEATURE_DIM

    def _session_features_from_dict(self, session: dict) -> list:
        """Extract 15 numeric session features from a runtime session dict."""
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
            # Feature 2 — ip_cache enrichment
            min(float(session.get("abuse_score") or 0), 100) / 100.0,
            1 if session.get("is_tor") else 0,
            1 if session.get("is_hosting") else 0,
            1 if session.get("threatfox_hit") else 0,
            # Feature 3 — timing regularity
            float(session.get("timing_std_norm", 0.5)),
        ]

    # ── Inference ─────────────────────────────────────────────────────────────

    def score_request(self, req: dict) -> dict:
        """
        Synchronous per-request scoring. Returns empty dict before first training.
        req keys: body_len, path, method, headers, flagged_count, is_c2,
                  is_tor, abuse_score, is_hosting, threatfox_hit, category, hour_of_day
        """
        if not self._trained:
            return {}

        try:
            import numpy as np
            feats = np.array([self._request_features_from_dict(req)], dtype=float)

            result = {}
            anomaly_score = 0.0
            risk_score    = 0.0

            # Anomaly score: decision_function returns negative = anomalous
            if self._iso_forest:
                raw = self._iso_forest.decision_function(feats)[0]
                # Normalise to 0–1 where 1 = most anomalous
                score = float(1.0 - (raw + 0.5))
                anomaly_score = round(max(0.0, min(1.0, score)), 3)
                result["anomaly_score"] = anomaly_score

            # Risk probability (HIGH or CRITICAL)
            if self._risk_clf:
                proba = self._risk_clf.predict_proba(feats)[0]
                # Sum probabilities for HIGH (idx 2) and CRITICAL (idx 3)
                n_classes = len(proba)
                high_prob = sum(proba[i] for i in range(n_classes) if i >= 2)
                risk_score = round(float(high_prob), 3)
                result["risk_score"] = risk_score

            # Feature 5 — Composite threat score
            geo_score = self.score_geo(req.get("country"), req.get("asn")) or 0.5
            composite = (
                0.25 * anomaly_score +
                0.35 * risk_score +
                0.20 * geo_score
                # bot contribution at session level only — use 0 here
            )
            composite = round(composite, 3)
            result["composite_score"] = composite
            result["georisk_score"]   = geo_score
            result["threat_band"] = (
                "CRITICAL" if composite >= 0.75 else
                "HIGH"     if composite >= 0.50 else
                "MEDIUM"   if composite >= 0.30 else "LOW"
            )

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
            import statistics

            async with get_db() as db:
                # Session aggregate
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

                # Feature 3 — timing std dev (last 20 requests)
                ts_cur = await db.execute(
                    "SELECT timestamp FROM requests WHERE ip = ? ORDER BY timestamp DESC LIMIT 20",
                    (ip,),
                )
                ts_rows = await ts_cur.fetchall()

                # Feature 2 — ip_cache enrichment for this IP
                cache_cur = await db.execute(
                    "SELECT abuse_score, is_tor, hosting, threatfox_hit FROM ip_cache WHERE ip = ?",
                    (ip,),
                )
                cache_row = await cache_cur.fetchone()

            if not row or row["cnt"] < 1:
                return {"cluster_id": self._cluster_registry.get(ip)}

            # Timing std dev
            timing_std_norm = 0.5
            if len(ts_rows) >= 3:
                try:
                    timestamps = sorted([
                        dt.fromisoformat(r["timestamp"].replace("Z", "+00:00")).timestamp()
                        for r in ts_rows
                    ])
                    gaps = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
                    if len(gaps) >= 2:
                        std = statistics.stdev(gaps)
                        timing_std_norm = min(std, 3600) / 3600
                except Exception:
                    pass

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
                # Feature 2 — ip_cache enrichment
                "abuse_score":         float(cache_row["abuse_score"] or 0) if cache_row else 0.0,
                "is_tor":              bool(cache_row["is_tor"])    if cache_row else False,
                "is_hosting":          bool(cache_row["hosting"])   if cache_row else False,
                "threatfox_hit":       bool(cache_row["threatfox_hit"]) if cache_row else False,
                # Feature 3 — timing regularity
                "timing_std_norm":     timing_std_norm,
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

    # ── Feature 4 — GeoRisk scoring ───────────────────────────────────────────

    def score_geo(self, country: str | None, asn: str | None) -> float | None:
        """
        Bayesian country/ASN risk score (0–1).
        Returns None before first training.
        """
        if not self._country_risk and not self._asn_risk:
            return None
        c = self._country_risk.get(country or "?", 0.5)
        a = self._asn_risk.get(asn or "?", 0.5)
        return round(0.35 * c + 0.65 * a, 3)

    # ── Stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Summary stats for the /api/ml/stats endpoint."""
        cluster_counts: dict[int, int] = {}
        for cid in self._cluster_registry.values():
            cluster_counts[cid] = cluster_counts.get(cid, 0) + 1

        # Build cluster_summary as an array (consumed by JS .filter())
        cluster_summary = [
            {"cluster_id": cid, "ip_count": cnt}
            for cid, cnt in sorted(cluster_counts.items())
            if cid != -1
        ]

        # Feature 4 — top risky countries/ASNs
        top_countries = sorted(
            [{"country": c, "score": s} for c, s in self._country_risk.items() if c != "?"],
            key=lambda x: x["score"], reverse=True
        )[:5]
        top_asns = sorted(
            [{"asn": a, "score": s} for a, s in self._asn_risk.items() if a != "?"],
            key=lambda x: x["score"], reverse=True
        )[:5]

        return {
            "trained":            self._trained,
            "total_samples":      self._total_samples,
            "min_samples_needed": MIN_SAMPLES_TO_TRAIN,
            "samples_at_last_train": self._samples_at_last_train,
            "last_trained":       self._last_train_time.isoformat() if self._last_train_time else None,
            # Feature 1 — real counters
            "anomalies_24h":      self._anomalies_24h,
            "bots_detected":      self._bots_detected,
            "models": {
                "anomaly_detection": self._iso_forest is not None,
                "risk_enhancement":  self._risk_clf   is not None,
                "bot_detection":     self._bot_clf     is not None,
                "clustering":        bool(self._cluster_registry),
                "geo_risk":          bool(self._country_risk),
            },
            "cluster_summary": cluster_summary,
            "noise_count":     cluster_counts.get(-1, 0),
            # Feature 4 — geo risk intel
            "top_risky_countries": top_countries,
            "top_risky_asns":      top_asns,
            # Feature 5 — composite percentile calibration
            "composite_percentiles": {
                "p10": self._composite_p10,
                "p50": self._composite_p50,
                "p90": self._composite_p90,
            },
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
engine = MLEngine()
