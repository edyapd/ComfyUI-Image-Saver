import os
from datetime import datetime
from sys import float_info
import json
import piexif
import piexif.helper
from PIL import Image
from PIL.PngImagePlugin import PngInfo
import numpy as np
import folder_paths
import comfy.sd
from .utils import get_sha256
from .prompt_metadata_extractor import PromptMetadataExtractor
from nodes import MAX_RESOLUTION


def parse_checkpoint_name(ckpt_name):
    return os.path.basename(ckpt_name)


def parse_checkpoint_name_without_extension(ckpt_name):
    return os.path.splitext(parse_checkpoint_name(ckpt_name))[0]


def handle_whitespace(string: str):
    return string.strip().replace("\n", " ").replace("\r", " ").replace("\t", " ")


def get_timestamp(time_format):
    now = datetime.now()
    try:
        timestamp = now.strftime(time_format)
    except:
        timestamp = now.strftime("%Y-%m-%d-%H%M%S")

    return timestamp

def save_json(image_info, filename):
    try:
        workflow = (image_info or {}).get('workflow')
        if workflow is None:
            print('No image info found, skipping saving of JSON')
        with open(f'{filename}.json', 'w') as workflow_file:
            json.dump(workflow, workflow_file)
            print(f'Saved workflow to {filename}.json')
    except Exception as e:
        print(f'Failed to save workflow as json due to: {e}, proceeding with the remainder of saving execution')


def make_pathname(filename, seed, modelname, counter, time_format, sampler_name, steps, cfg, scheduler, denoise):
    filename = filename.replace("%date", get_timestamp("%Y-%m-%d"))
    filename = filename.replace("%time", get_timestamp(time_format))
    filename = filename.replace("%model", parse_checkpoint_name(modelname))
    filename = filename.replace("%seed", str(seed))
    filename = filename.replace("%counter", str(counter))
    filename = filename.replace("%sampler_name", sampler_name)
    filename = filename.replace("%steps", str(steps))
    filename = filename.replace("%cfg", str(cfg))
    filename = filename.replace("%scheduler", scheduler)
    filename = filename.replace("%basemodelname", parse_checkpoint_name_without_extension(modelname))
    filename = filename.replace("%denoise", str(denoise))
    return filename

def make_filename(filename, seed, modelname, counter, time_format, sampler_name, steps, cfg, scheduler, denoise):
    filename = make_pathname(filename, seed, modelname, counter, time_format, sampler_name, steps, cfg, scheduler, denoise)
    return get_timestamp(time_format) if filename == "" else filename

class SeedGenerator:
    RETURN_TYPES = ("INT",)
    OUTPUT_TOOLTIPS = ("seed (INT)",)
    FUNCTION = "get_seed"

    CATEGORY = "ImageSaver/utils"
    DESCRIPTION = "Provides seed as integer"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff, "tooltip": "seed as integer number"}),
            }
        }

    def get_seed(self, seed):
        return (seed,)

class StringLiteral:
    RETURN_TYPES = ("STRING",)
    OUTPUT_TOOLTIPS = ("string (STRING)",)
    FUNCTION = "get_string"

    CATEGORY = "ImageSaver/utils"
    DESCRIPTION = "Provides a string"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "string": ("STRING", {"default": "", "multiline": True, "tooltip": "string"}),
            }
        }

    def get_string(self, string):
        return (string,)

class SizeLiteral:
    RETURN_TYPES = ("INT",)
    RETURN_NAMES = ("size",)
    OUTPUT_TOOLTIPS = ("size (INT)",)
    FUNCTION = "get_int"

    CATEGORY = "ImageSaver/utils"
    DESCRIPTION = f"Provides integer number between 0 and {MAX_RESOLUTION} (step=8)"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "int": ("INT", {"default": 512, "min": 0, "max": MAX_RESOLUTION, "step": 8, "tooltip": "size as integer (in steps of 8)"}),
            }
        }

    def get_int(self, int):
        return (int,)

class IntLiteral:
    RETURN_TYPES = ("INT",)
    OUTPUT_TOOLTIPS = ("int (INT)",)
    FUNCTION = "get_int"

    CATEGORY = "ImageSaver/utils"
    DESCRIPTION = "Provides integer number between 0 and 1000000"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "int": ("INT", {"default": 0, "min": 0, "max": 1000000, "tooltip": "integer number"}),
            }
        }

    def get_int(self, int):
        return (int,)

class FloatLiteral:
    RETURN_TYPES = ("FLOAT",)
    OUTPUT_TOOLTIPS = ("float (FLOAT)",)
    FUNCTION = "get_float"

    CATEGORY = "ImageSaver/utils"
    DESCRIPTION = f"Provides a floating point number between {float_info.min} and {float_info.max} (step=0.01)"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "float": ("FLOAT", {"default": 1.0, "min": float_info.min, "max": float_info.max, "step": 0.01, "tooltip": "floating point number"}),
            }
        }

    def get_float(self, float):
        return (float,)

class CfgLiteral:
    RETURN_TYPES = ("FLOAT",)
    RETURN_NAMES = ("value",)
    OUTPUT_TOOLTIPS = ("cfg (FLOAT)",)
    FUNCTION = "get_float"

    CATEGORY = "ImageSaver/utils"
    DESCRIPTION = "Provides CFG value between 0.0 and 100.0"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "float": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0, "tooltip": "CFG as a floating point number"}),
            }
        }

    def get_float(self, float):
        return (float,)

class CheckpointLoaderWithName:
    RETURN_TYPES = ("MODEL", "CLIP", "VAE", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "VAE", "model_name")
    OUTPUT_TOOLTIPS = ("U-Net model (denoising latents)", "CLIP (Contrastive Language-Image Pre-Training) model (encoding text prompts)", "VAE (Variational autoencoder) model (latent<->pixel encoding/decoding)", "checkpoint name")
    FUNCTION = "load_checkpoint"

    CATEGORY = "ImageSaver/utils"
    DESCRIPTION = "Loads U-Net model, CLIP model and VAE model from a checkpoint file"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "ckpt_name": (folder_paths.get_filename_list("checkpoints"), {"tooltip": "checkpoint"}),
            }
        }

    def load_checkpoint(self, ckpt_name, output_vae=True, output_clip=True):
        ckpt_path = folder_paths.get_full_path("checkpoints", ckpt_name)
        out = comfy.sd.load_checkpoint_guess_config(ckpt_path, output_vae=True, output_clip=True, embedding_directory=folder_paths.get_folder_paths("embeddings"))

        # add checkpoint name to the output tuple (without the ClipVisionModel)
        out = (*out[:3], ckpt_name)
        return out

class SamplerSelector:
    RETURN_TYPES = (comfy.samplers.KSampler.SAMPLERS, "STRING")
    RETURN_NAMES = ("sampler",                        "sampler_name")
    OUTPUT_TOOLTIPS = ("sampler (SAMPLERS)", "sampler name (STRING)")
    FUNCTION = "get_names"

    CATEGORY = 'ImageSaver/utils'
    DESCRIPTION = 'Provides one of the available ComfyUI samplers'

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS, {"tooltip": "sampler (Comfy's standard)"}),
            }
        }

    def get_names(self, sampler_name):
        return (sampler_name, sampler_name)

class SchedulerSelector:
    RETURN_TYPES = (comfy.samplers.KSampler.SCHEDULERS + ['AYS SDXL', 'AYS SD1', 'AYS SVD', 'GITS[coeff=1.2]'], "STRING")
    RETURN_NAMES = ("scheduler",                                                                                "scheduler_name")
    OUTPUT_TOOLTIPS = ("scheduler (SCHEDULERS + ['AYS SDXL', 'AYS SD1', 'AYS SVD', 'GITS[coeff=1.2]'])", "scheduler name (STRING)")
    FUNCTION = "get_names"

    CATEGORY = 'ImageSaver/utils'
    DESCRIPTION = 'Provides one of the standard ComfyUI plus some extra schedulers'

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS + ['AYS SDXL', 'AYS SD1', 'AYS SVD', 'GITS[coeff=1.2]'], {"tooltip": "scheduler (Comfy's standard + extras)"}),
            }
        }

    def get_names(self, scheduler):
        return (scheduler, scheduler)

class SchedulerSelectorComfy:
    RETURN_TYPES = (comfy.samplers.KSampler.SCHEDULERS, "STRING")
    RETURN_NAMES = ("scheduler",                        "scheduler_name")
    OUTPUT_TOOLTIPS = ("scheduler (SCHEDULERS)", "scheduler name (STRING)")
    FUNCTION = "get_names"

    CATEGORY = 'ImageSaver/utils'
    DESCRIPTION = 'Provides one of the standard ComfyUI schedulers'

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS, {"tooltip": "scheduler (Comfy's standard)"}),
            }
        }

    def get_names(self, scheduler):
        return (scheduler, scheduler)

class SchedulerToString:
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("scheduler_name",)
    OUTPUT_TOOLTIPS = ("scheduler name (STRING)",)
    FUNCTION = "get_name"

    CATEGORY = 'ImageSaver/utils'
    DESCRIPTION = 'Provides a given sandard ComfyUI or some extra scheduler\'s name as string'

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS + ['AYS SDXL', 'AYS SD1', 'AYS SVD', 'GITS[coeff=1.2]'], {"tooltip": "scheduler (Comfy's standard + extras)"}),
            }
        }

    def get_name(self, scheduler):
        return (scheduler,)

class SchedulerComfyToString:
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("scheduler_name",)
    OUTPUT_TOOLTIPS = ("scheduler name (STRING)",)
    FUNCTION = "get_name"

    CATEGORY = 'ImageSaver/utils'
    DESCRIPTION = 'Provides a given sandard ComfyUI scheduler\'s name as string'

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS, {"tooltip": "scheduler (Comfy's standard)"}),
            }
        }

    def get_name(self, scheduler):
        return (scheduler,)

class SamplerToString:
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("sampler_name",)
    OUTPUT_TOOLTIPS = ("sampler name (STRING)",)
    FUNCTION = "get_name"

    CATEGORY = 'ImageSaver/utils'
    DESCRIPTION = 'Provides a given sandard ComfyUI samplers\'s name as string'

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "sampler": (comfy.samplers.KSampler.SAMPLERS, {"tooltip": "sampler (Comfy's standard)"}),
            }
        }

    def get_name(self, sampler):
        return (sampler,)

class ImageSaver:
    def __init__(self):
        self.output_dir = folder_paths.output_directory
        self.civitai_sampler_map = {
            'euler_ancestral': 'Euler a',
            'euler': 'Euler',
            'lms': 'LMS',
            'heun': 'Heun',
            'dpm_2': 'DPM2',
            'dpm_2_ancestral': 'DPM2 a',
            'dpmpp_2s_ancestral': 'DPM++ 2S a',
            'dpmpp_2m': 'DPM++ 2M',
            'dpmpp_sde': 'DPM++ SDE',
            'dpmpp_2m_sde': 'DPM++ 2M SDE',
            'dpmpp_3m_sde': 'DPM++ 3M SDE',
            'dpm_fast': 'DPM fast',
            'dpm_adaptive': 'DPM adaptive',
            'ddim': 'DDIM',
            'plms': 'PLMS',
            'uni_pc_bh2': 'UniPC',
            'uni_pc': 'UniPC',
            'lcm': 'LCM',
        }

    def get_civitai_sampler_name(self, sampler_name, scheduler):
        # based on: https://github.com/civitai/civitai/blob/main/src/server/common/constants.ts#L122
        if sampler_name in self.civitai_sampler_map:
            civitai_name = self.civitai_sampler_map[sampler_name]

            if scheduler == "karras":
                civitai_name += " Karras"
            elif scheduler == "exponential":
                civitai_name += " Exponential"

            return civitai_name
        else:
            if scheduler != 'normal':
                return f"{sampler_name}_{scheduler}"
            else:
                return sampler_name

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images":                ("IMAGE",   {                                                             "tooltip": "image(s) to save"}),
                "filename":              ("STRING",  {"default": '%time_%basemodelname_%seed', "multiline": False, "tooltip": "filename (available variables: %date, %time, %model, %seed, %counter, %sampler_name, %steps, %cfg, %scheduler, %basemodelname, %denoise)"}),
                "path":                  ("STRING",  {"default": '', "multiline": False,                           "tooltip": "path to save the images (under Comfy's save directory)"}),
                "extension":             (['png', 'jpeg', 'webp'], {                                               "tooltip": "file extension/type to save image as"}),
            },
            "optional": {
                "steps":                 ("INT",     {"default": 20, "min": 1, "max": 10000,                       "tooltip": "number of steps"}),
                "cfg":                   ("FLOAT",   {"default": 7.0, "min": 0.0, "max": 100.0,                    "tooltip": "CFG value"}),
                "modelname":             ("STRING",  {"default": '', "multiline": False,                           "tooltip": "model name"}),
                "sampler_name":          ("STRING",  {"default": '', "multiline": False,                           "tooltip": "sampler name (as string)"}),
                "scheduler":             ("STRING",  {"default": 'normal', "multiline": False,                     "tooltip": "scheduler name (as string)"}),
                "positive":              ("STRING",  {"default": 'unknown', "multiline": True,                     "tooltip": "positive prompt"}),
                "negative":              ("STRING",  {"default": 'unknown', "multiline": True,                     "tooltip": "negative prompt"}),
                "seed_value":            ("INT",     {"default": 0, "min": 0, "max": 0xffffffffffffffff,           "tooltip": "seed"}),
                "width":                 ("INT",     {"default": 512, "min": 0, "max": MAX_RESOLUTION, "step": 8,  "tooltip": "image width"}),
                "height":                ("INT",     {"default": 512, "min": 0, "max": MAX_RESOLUTION, "step": 8,  "tooltip": "image height"}),
                "lossless_webp":         ("BOOLEAN", {"default": True,                                             "tooltip": "if True, saved WEBP files will be lossless"}),
                "quality_jpeg_or_webp":  ("INT",     {"default": 100, "min": 1, "max": 100,                        "tooltip": "quality setting of JPEG/WEBP"}),
                "optimize_png":          ("BOOLEAN", {"default": False,                                            "tooltip": "if True, saved PNG files will be optimized (can reduce file size but is slower)"}),
                "counter":               ("INT",     {"default": 0, "min": 0, "max": 0xffffffffffffffff,           "tooltip": "counter"}),
                "denoise":               ("FLOAT",   {"default": 1.0, "min": 0.0, "max": 1.0,                      "tooltip": "denoise value"}),
                "time_format":           ("STRING",  {"default": "%Y-%m-%d-%H%M%S", "multiline": False,            "tooltip": "timestamp format"}),
                "save_workflow_as_json": ("BOOLEAN", {"default": False,                                            "tooltip": "if True, saves the workflow as a separate JSON file, in addition to saving the image"}),
                "embed_workflow_in_png": ("BOOLEAN", {"default": True,                                             "tooltip": "if True, embeds the workflow in the saved PNG file (if saving as PNG)"}),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "save_files"

    OUTPUT_NODE = True

    CATEGORY = "ImageSaver"
    DESCRIPTION = "Save images with civitai-compatible generation metadata"

    def save_files(
        self,
        images,
        seed_value,
        steps,
        cfg,
        sampler_name,
        scheduler,
        positive,
        negative,
        modelname,
        quality_jpeg_or_webp,
        lossless_webp,
        optimize_png,
        width,
        height,
        counter,
        filename,
        path,
        extension,
        time_format,
        denoise,
        save_workflow_as_json=False,
        embed_workflow_in_png=True,
        prompt=None,
        extra_pnginfo=None,
    ):
        filename = make_filename(filename, seed_value, modelname, counter, time_format, sampler_name, steps, cfg, scheduler, denoise)
        path = make_pathname(path, seed_value, modelname, counter, time_format, sampler_name, steps, cfg, scheduler, denoise)
        ckpt_path = folder_paths.get_full_path("checkpoints", modelname)

        if ckpt_path:
            modelhash = get_sha256(ckpt_path)[:10]
        else:
            modelhash = ""

        metadata_extractor = PromptMetadataExtractor([positive, negative])
        embeddings = metadata_extractor.get_embeddings()
        loras = metadata_extractor.get_loras()
        civitai_sampler_name = self.get_civitai_sampler_name(sampler_name.replace('_gpu', ''), scheduler)

        extension_hashes = json.dumps(embeddings | loras | { "model": modelhash })
        basemodelname = parse_checkpoint_name_without_extension(modelname)

        positive_a111_params = handle_whitespace(positive)
        negative_a111_params = f"\nNegative prompt: {handle_whitespace(negative)}"
        a111_params = f"{positive_a111_params}{negative_a111_params}\nSteps: {steps}, Sampler: {civitai_sampler_name}, CFG scale: {cfg}, Seed: {seed_value}, Size: {width}x{height}, Model hash: {modelhash}, Model: {basemodelname}, Hashes: {extension_hashes}, Version: ComfyUI"

        output_path = os.path.join(self.output_dir, path)

        if output_path.strip() != '':
            if not os.path.exists(output_path.strip()):
                print(f'The path `{output_path.strip()}` specified doesn\'t exist! Creating directory.')
                os.makedirs(output_path, exist_ok=True)

        filenames = self.save_images(images, output_path, filename, a111_params, extension, quality_jpeg_or_webp, lossless_webp, optimize_png, prompt, extra_pnginfo, save_workflow_as_json, embed_workflow_in_png)

        subfolder = os.path.normpath(path)
        return {"ui": {"images": map(lambda filename: {"filename": filename, "subfolder": subfolder if subfolder != '.' else '', "type": 'output'}, filenames)}}

    def save_images(self, images, output_path, filename_prefix, a111_params, extension, quality_jpeg_or_webp, lossless_webp, optimize_png, prompt, extra_pnginfo, save_workflow_as_json, embed_workflow_in_png) -> list[str]:
        img_count = 1
        paths = list()
        for image in images:
            i = 255. * image.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))

            if images.size()[0] > 1:
                current_filename_prefix = "{}_{:02d}".format(filename_prefix, img_count)
            else:
                current_filename_prefix = filename_prefix

            if extension == 'png':
                metadata = PngInfo()
                metadata.add_text("parameters", a111_params)

                # embed workflow and prompt json only if embed_workflow_in_png is true
                if embed_workflow_in_png:
                    if prompt is not None:
                        metadata.add_text("prompt", json.dumps(prompt))
                    if extra_pnginfo is not None:
                        for x in extra_pnginfo:
                            metadata.add_text(x, json.dumps(extra_pnginfo[x]))

                filename = f"{current_filename_prefix}.png"
                img.save(os.path.join(output_path, filename), pnginfo=metadata, optimize=optimize_png)
            else:
                filename = f"{current_filename_prefix}.{extension}"
                file = os.path.join(output_path, filename)
                img.save(file, optimize=True, quality=quality_jpeg_or_webp, lossless=lossless_webp)
                exif_bytes = piexif.dump({
                    "Exif": {
                        piexif.ExifIFD.UserComment: piexif.helper.UserComment.dump(a111_params, encoding="unicode")
                    },
                })
                piexif.insert(exif_bytes, file)

            if save_workflow_as_json:
                save_json(extra_pnginfo, os.path.join(output_path, current_filename_prefix))

            paths.append(filename)
            img_count += 1
        return paths


NODE_CLASS_MAPPINGS = {
    "Checkpoint Loader with Name (Image Saver)": CheckpointLoaderWithName,
    "Image Saver": ImageSaver,
    "Sampler Selector (Image Saver)": SamplerSelector,
    "Scheduler Selector (Image Saver)": SchedulerSelector,
    "Scheduler Selector (Comfy) (Image Saver)": SchedulerSelectorComfy,
    "Seed Generator (Image Saver)": SeedGenerator,
    "String Literal (Image Saver)": StringLiteral,
    "Width/Height Literal (Image Saver)": SizeLiteral,
    "Cfg Literal (Image Saver)": CfgLiteral,
    "Int Literal (Image Saver)": IntLiteral,
    "Float Literal (Image Saver)": FloatLiteral,
    "SchedulerToString (Image Saver)": SchedulerToString,
    "SchedulerComfyToString (Image Saver)": SchedulerComfyToString,
    "SamplerToString (Image Saver)": SamplerToString,
}
