"""Draw the Hazz Wispr app icon (gradient squircle + waveform) as a 1024px PNG."""

import sys

import AppKit

SIZE = 1024
BARS = [0.22, 0.40, 0.60, 0.40, 0.22]  # bar heights as a fraction of the tile


def rgb(hex_):
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, 1)


def main(out):
    rep = AppKit.NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, SIZE, SIZE, 8, 4, True, False, AppKit.NSDeviceRGBColorSpace, 0, 0)
    AppKit.NSGraphicsContext.saveGraphicsState()
    AppKit.NSGraphicsContext.setCurrentContext_(AppKit.NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep))

    # macOS icon grid: 824px tile centred on a 1024px canvas.
    tile = AppKit.NSMakeRect(100, 100, 824, 824)
    shape = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(tile, 185, 185)
    gradient = AppKit.NSGradient.alloc().initWithColors_([rgb("#ff8a3d"), rgb("#ff3d6e"), rgb("#ff5a36")])
    gradient.drawInBezierPath_angle_(shape, -60)

    # Soft white highlight in the lower right, like light bleeding at the edge.
    shape.addClip()
    glow = AppKit.NSGradient.alloc().initWithStartingColor_endingColor_(
        AppKit.NSColor.colorWithWhite_alpha_(1, 0.35), AppKit.NSColor.colorWithWhite_alpha_(1, 0))
    glow.drawFromCenter_radius_toCenter_radius_options_((820, 180), 0, (820, 180), 520, 0)

    AppKit.NSColor.colorWithWhite_alpha_(0.05, 1).setFill()
    bar_w, gap = 74, 52
    x = 512 - (len(BARS) * bar_w + (len(BARS) - 1) * gap) / 2
    for h in BARS:
        height = 824 * h
        rect = AppKit.NSMakeRect(x, 512 - height / 2, bar_w, height)
        AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, bar_w / 2, bar_w / 2).fill()
        x += bar_w + gap

    AppKit.NSGraphicsContext.restoreGraphicsState()
    rep.representationUsingType_properties_(AppKit.NSBitmapImageFileTypePNG, None).writeToFile_atomically_(out, True)


if __name__ == "__main__":
    main(sys.argv[1])
