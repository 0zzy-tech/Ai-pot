"""
Fake Stable Diffusion WebUI (Automatic1111 / AUTOMATIC1111) API endpoints.
Also covers FORGE and similar SD forks that share the same API.

Real endpoints:
  GET  /sdapi/v1/sd-models
  GET  /sdapi/v1/sd-vae
  GET  /sdapi/v1/samplers
  GET  /sdapi/v1/upscalers
  GET  /sdapi/v1/schedulers
  GET  /sdapi/v1/options
  POST /sdapi/v1/options
  GET  /sdapi/v1/progress
  POST /sdapi/v1/txt2img
  POST /sdapi/v1/img2img
  POST /sdapi/v1/interrogate
  POST /sdapi/v1/interrupt
  GET  /sdapi/v1/memory
  GET  /info
"""

import base64
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()

# Minimal valid 1×1 white PNG encoded as base64
_FAKE_IMAGE_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=="
)

_FAKE_MODELS = [
    {
        "title":       "v1-5-pruned-emaonly.safetensors [6ce0161689]",
        "model_name":  "v1-5-pruned-emaonly",
        "hash":        "6ce0161689",
        "sha256":      "6ce0161689b3853acaa03779ec93eafe75a02f4ced659bee03f50797806fa2fa",
        "filename":    "/models/Stable-diffusion/v1-5-pruned-emaonly.safetensors",
        "config":      None,
    },
    {
        "title":       "dreamshaper_8.safetensors [879db523c3]",
        "model_name":  "dreamshaper_8",
        "hash":        "879db523c3",
        "sha256":      "879db523c30a49b4f15d77af6e5c462e19a75bc7ee1d37dde7c34a8ff2d0af3c",
        "filename":    "/models/Stable-diffusion/dreamshaper_8.safetensors",
        "config":      None,
    },
    {
        "title":       "realisticVisionV60B1_v51HyperVAE.safetensors [a0760b15b4]",
        "model_name":  "realisticVisionV60B1_v51HyperVAE",
        "hash":        "a0760b15b4",
        "sha256":      "a0760b15b49b0f4efee76c2c2b9c04e3d39a7d5b2d0b62c8a9fa5d3eb3d0c1e2",
        "filename":    "/models/Stable-diffusion/realisticVisionV60B1_v51HyperVAE.safetensors",
        "config":      None,
    },
]

_FAKE_SAMPLERS = [
    {"name": "Euler a",    "aliases": ["euler_ancestral"], "options": {}},
    {"name": "Euler",      "aliases": ["euler"],           "options": {}},
    {"name": "DPM++ 2M Karras", "aliases": ["dpm_2m_ka"], "options": {}},
    {"name": "DDIM",       "aliases": ["ddim"],            "options": {}},
    {"name": "UniPC",      "aliases": ["unipc"],           "options": {}},
    {"name": "LMS",        "aliases": ["lms"],             "options": {}},
]

_FAKE_UPSCALERS = [
    {"name": "None",       "model_name": None, "model_path": None, "model_url": None, "scale": 4},
    {"name": "Lanczos",    "model_name": None, "model_path": None, "model_url": None, "scale": 4},
    {"name": "ESRGAN_4x",  "model_name": "ESRGAN_4x", "model_path": "/models/ESRGAN/ESRGAN_4x.pth", "model_url": None, "scale": 4},
    {"name": "R-ESRGAN 4x+", "model_name": "RealESRGAN_x4plus", "model_path": "/models/RealESRGAN/RealESRGAN_x4plus.pth", "model_url": None, "scale": 4},
]


def _image_response(prompt: str = "", n: int = 1) -> dict:
    """Returns a fake txt2img/img2img response."""
    return {
        "images":     [_FAKE_IMAGE_B64] * max(1, n),
        "parameters": {
            "prompt":          prompt[:200],
            "negative_prompt": "",
            "styles":          [],
            "seed":            42,
            "subseed":         -1,
            "sampler_name":    "Euler a",
            "scheduler":       "Automatic",
            "steps":           20,
            "cfg_scale":       7.0,
            "width":           512,
            "height":          512,
            "denoising_strength": 0.0,
        },
        "info": (
            '{"prompt":"' + prompt[:100].replace('"', '\\"') + '",'
            '"seed":42,"sampler_name":"Euler a","steps":20,'
            '"cfg_scale":7.0,"width":512,"height":512}'
        ),
    }


# ── Model / config endpoints ──────────────────────────────────────────────────

@router.get("/sdapi/v1/sd-models")
async def sd_models():
    return JSONResponse(content=_FAKE_MODELS)


@router.get("/sdapi/v1/sd-vae")
async def sd_vae():
    return JSONResponse(content=[
        {"model_name": "Automatic", "filename": "Automatic"},
        {"model_name": "vae-ft-mse-840000-ema-pruned.safetensors",
         "filename":   "/models/VAE/vae-ft-mse-840000-ema-pruned.safetensors"},
    ])


@router.get("/sdapi/v1/samplers")
async def sd_samplers():
    return JSONResponse(content=_FAKE_SAMPLERS)


@router.get("/sdapi/v1/schedulers")
async def sd_schedulers():
    return JSONResponse(content=[
        {"name": "Automatic", "label": "Automatic", "aliases": None, "default_rho": -1, "timestep_spacing": ""},
        {"name": "Karras",    "label": "Karras",    "aliases": None, "default_rho": -1, "timestep_spacing": ""},
        {"name": "Exponential","label": "Exponential","aliases": None,"default_rho": -1, "timestep_spacing": ""},
    ])


@router.get("/sdapi/v1/upscalers")
async def sd_upscalers():
    return JSONResponse(content=_FAKE_UPSCALERS)


@router.get("/sdapi/v1/loras")
async def sd_loras():
    return JSONResponse(content=[
        {"name": "add_detail", "alias": "add_detail", "path": "/models/Lora/add_detail.safetensors", "metadata": {}},
    ])


@router.get("/sdapi/v1/options")
async def sd_get_options():
    return JSONResponse(content={
        "sd_model_checkpoint":   _FAKE_MODELS[0]["title"],
        "sd_vae":                "Automatic",
        "CLIP_stop_at_last_layers": 1,
        "eta_noise_seed_delta":  0,
        "img2img_color_correction": False,
        "samples_save":          True,
        "samples_format":        "png",
        "outdir_samples":        "",
        "outdir_txt2img_samples": "outputs/txt2img-images",
        "outdir_img2img_samples": "outputs/img2img-images",
    })


@router.post("/sdapi/v1/options")
async def sd_set_options():
    return JSONResponse(content={})


@router.get("/sdapi/v1/memory")
async def sd_memory():
    return JSONResponse(content={
        "ram":  {"free": 8_000_000_000, "used": 2_000_000_000, "total": 10_000_000_000},
        "cuda": {"system": {"free": 6_000_000_000, "used": 2_000_000_000, "total": 8_000_000_000},
                 "active": {"current": 1_800_000_000, "peak": 3_200_000_000},
                 "reserved": {"current": 2_000_000_000, "peak": 3_500_000_000}},
    })


# ── Progress ──────────────────────────────────────────────────────────────────

@router.get("/sdapi/v1/progress")
async def sd_progress():
    return JSONResponse(content={
        "progress":          0.0,
        "eta_relative":      0.0,
        "state":             {"skipped": False, "interrupted": False, "stopping_generation": False,
                              "job": "", "job_count": 0, "job_timestamp": "0",
                              "job_no": 0, "sampling_step": 0, "sampling_steps": 0},
        "current_image":     None,
        "textinfo":          None,
    })


# ── Generation ────────────────────────────────────────────────────────────────

@router.post("/sdapi/v1/txt2img")
async def sd_txt2img(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    prompt = body.get("prompt", "")
    n      = body.get("batch_size", 1)
    return JSONResponse(content=_image_response(prompt, n))


@router.post("/sdapi/v1/img2img")
async def sd_img2img(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    prompt = body.get("prompt", "")
    n      = body.get("batch_size", 1)
    return JSONResponse(content=_image_response(prompt, n))


# ── Interrogate (image → prompt) ──────────────────────────────────────────────

@router.post("/sdapi/v1/interrogate")
async def sd_interrogate(request: Request):
    return JSONResponse(content={
        "caption": "a beautiful landscape with mountains and a lake, high quality, detailed"
    })


# ── Interrupt / Skip ──────────────────────────────────────────────────────────

@router.post("/sdapi/v1/interrupt")
async def sd_interrupt():
    return JSONResponse(content={})


@router.post("/sdapi/v1/skip")
async def sd_skip():
    return JSONResponse(content={})


# ── /info (general app info) ──────────────────────────────────────────────────

@router.get("/info")
async def sd_info():
    return JSONResponse(content={
        "title":   "Stable Diffusion WebUI",
        "version": "1.10.1",
        "commit":  "a9fed7c364",
        "script_list": [],
        "is_api": True,
    })
