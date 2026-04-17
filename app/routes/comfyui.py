"""
Fake ComfyUI API endpoints.
ComfyUI is the leading node-based Stable Diffusion / image generation UI.

Real endpoints:
  GET  /system_stats
  GET  /object_info
  GET  /object_info/{node_class}
  GET  /history
  GET  /history/{prompt_id}
  GET  /queue
  POST /prompt
  POST /interrupt
  POST /free
  GET  /view?filename=...&type=output
  GET  /upload/image      (multipart)
  POST /upload/image
"""

import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

router = APIRouter()

# Fake 1×1 transparent PNG
_FAKE_IMAGE_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6260000000000200012f7c3f0000000049454e44ae426082"
)

# In-memory fake queue state
_fake_queue: list[dict] = []


# ── GET /system_stats ─────────────────────────────────────────────────────────

@router.get("/system_stats")
async def comfyui_system_stats():
    return JSONResponse(content={
        "system": {
            "os":          "posix",
            "ram_total":   16_000_000_000,
            "ram_free":    8_000_000_000,
            "comfyui_version": "0.3.10",
            "python_version":  "3.11.7",
            "pytorch_version": "2.1.2+cu121",
            "embedded_python": False,
            "argv": ["/home/pi/ComfyUI/main.py"],
        },
        "devices": [
            {
                "name":          "cuda:0 NVIDIA GeForce RTX 3080",
                "type":          "cuda",
                "index":         0,
                "vram_total":    10_737_418_240,
                "vram_free":     6_442_450_944,
                "torch_vram_total": 10_737_418_240,
                "torch_vram_free":  5_368_709_120,
            }
        ],
    })


# ── GET /object_info ──────────────────────────────────────────────────────────

@router.get("/object_info")
async def comfyui_object_info():
    # Return a minimal but convincing subset of node types
    return JSONResponse(content={
        "KSampler": {
            "input": {
                "required": {
                    "model":       ["MODEL"],
                    "seed":        ["INT", {"default": 0, "min": 0, "max": 2**32}],
                    "steps":       ["INT", {"default": 20, "min": 1, "max": 10000}],
                    "cfg":         ["FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0}],
                    "sampler_name":["euler", "euler_ancestral", "dpm_2", "ddim"],
                    "scheduler":   ["normal", "karras", "exponential", "simple"],
                    "positive":    ["CONDITIONING"],
                    "negative":    ["CONDITIONING"],
                    "latent_image":["LATENT"],
                    "denoise":     ["FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0}],
                }
            },
            "output":      ["LATENT"],
            "category":    "sampling",
            "description": "Denoises the latent image.",
        },
        "CheckpointLoaderSimple": {
            "input": {
                "required": {
                    "ckpt_name": [
                        "v1-5-pruned-emaonly.safetensors",
                        "dreamshaper_8.safetensors",
                    ]
                }
            },
            "output":   ["MODEL", "CLIP", "VAE"],
            "category": "loaders",
        },
        "CLIPTextEncode": {
            "input": {
                "required": {
                    "text":  ["STRING", {"multiline": True}],
                    "clip":  ["CLIP"],
                }
            },
            "output":   ["CONDITIONING"],
            "category": "conditioning",
        },
        "EmptyLatentImage": {
            "input": {
                "required": {
                    "width":  ["INT", {"default": 512}],
                    "height": ["INT", {"default": 512}],
                    "batch_size": ["INT", {"default": 1}],
                }
            },
            "output":   ["LATENT"],
            "category": "latent",
        },
        "VAEDecode": {
            "input": {"required": {"samples": ["LATENT"], "vae": ["VAE"]}},
            "output":   ["IMAGE"],
            "category": "latent",
        },
        "SaveImage": {
            "input": {
                "required": {
                    "images":        ["IMAGE"],
                    "filename_prefix": ["STRING", {"default": "ComfyUI"}],
                }
            },
            "output":   [],
            "output_node": True,
            "category": "image",
        },
    })


@router.get("/object_info/{node_class}")
async def comfyui_object_info_node(node_class: str):
    return JSONResponse(content={})


# ── GET /queue ─────────────────────────────────────────────────────────────────

@router.get("/queue")
async def comfyui_queue():
    return JSONResponse(content={
        "queue_running": [],
        "queue_pending": [],
    })


# ── GET /history ──────────────────────────────────────────────────────────────

@router.get("/history")
async def comfyui_history():
    return JSONResponse(content={})


@router.get("/history/{prompt_id}")
async def comfyui_history_item(prompt_id: str):
    return JSONResponse(content={
        prompt_id: {
            "prompt":    [0, prompt_id, {}, {"client_id": "fake"}, []],
            "outputs":   {
                "9": {
                    "images": [
                        {"filename": f"ComfyUI_{prompt_id[:8]}_00001_.png", "subfolder": "", "type": "output"}
                    ]
                }
            },
            "status": {"status_str": "success", "completed": True, "messages": []},
        }
    })


# ── POST /prompt ──────────────────────────────────────────────────────────────

@router.post("/prompt")
async def comfyui_prompt(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    prompt_id = uuid.uuid4().hex
    return JSONResponse(content={
        "prompt_id":  prompt_id,
        "number":     len(_fake_queue) + 1,
        "node_errors": {},
    })


# ── POST /interrupt ───────────────────────────────────────────────────────────

@router.post("/interrupt")
async def comfyui_interrupt():
    return JSONResponse(content={})


# ── POST /free ────────────────────────────────────────────────────────────────

@router.post("/free")
async def comfyui_free():
    return JSONResponse(content={})


# ── GET /view (return fake image) ────────────────────────────────────────────

@router.get("/view")
async def comfyui_view(filename: str = "", subfolder: str = "", type: str = "output"):
    return Response(
        content=_FAKE_IMAGE_BYTES,
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
