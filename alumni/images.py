"""Traitement des images envoyées (redimensionnement, JPEG)."""
import io


def compress_jpeg(uploaded, max_side: int, quality: int) -> bytes:
    """Redimensionne à `max_side` pixels maximum et renvoie un JPEG. Lève une exception si ce n'est pas une image."""
    from PIL import Image, ImageOps

    image = Image.open(uploaded)
    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.getchannel("A"))
        image = background
    else:
        image = image.convert("RGB")
    image.thumbnail((max_side, max_side))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()
