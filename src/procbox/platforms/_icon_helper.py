from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) != 2:
        return 1

    try:
        from AppKit import (
            NSBitmapImageRep,
            NSCalibratedRGBColorSpace,
            NSGraphicsContext,
            NSMakeRect,
            NSWorkspace,
        )

        size = 256
        image = NSWorkspace.sharedWorkspace().iconForFile_(sys.argv[1])
        if image is None:
            return 1

        rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(  # noqa: E501
            None,
            size,
            size,
            8,
            4,
            True,
            False,
            NSCalibratedRGBColorSpace,
            0,
            0,
        )
        if rep is None:
            return 1

        context = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
        if context is None:
            return 1
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.setCurrentContext_(context)
        image.drawInRect_(NSMakeRect(0, 0, size, size))
        NSGraphicsContext.restoreGraphicsState()

        data = rep.representationUsingType_properties_(4, {})
        if data is None:
            return 1
        sys.stdout.buffer.write(bytes(data))
        sys.stdout.buffer.flush()
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
