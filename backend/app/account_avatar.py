from io import BytesIO

from fastapi import HTTPException
from PIL import Image, ImageOps

AVATAR_UPLOAD_LIMIT = 2 * 1024 * 1024


def normalize_avatar(payload: bytes) -> bytes:
    if len(payload) > AVATAR_UPLOAD_LIMIT:
        raise HTTPException(413, "Choose a profile picture no larger than 2 MB.")
    try:
        with Image.open(BytesIO(payload), formats=["JPEG", "PNG", "WEBP"]) as image:
            if image.width * image.height > 16_000_000:
                raise HTTPException(422, "Choose a photo under 16 megapixels.")
            if getattr(image, "is_animated", False):
                raise HTTPException(422, "Choose a still photo.")
            ImageOps.exif_transpose(image, in_place=True)
            with ImageOps.fit(
                image.convert("RGBA"), (192, 192), Image.Resampling.LANCZOS
            ) as avatar:
                avatar.info.clear()
                with BytesIO() as output:
                    avatar.save(output, format="PNG")
                    return output.getvalue()
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(
            415, "Choose a valid JPEG, PNG, or WebP profile picture."
        ) from exc
