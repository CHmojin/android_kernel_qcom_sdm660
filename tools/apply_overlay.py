#!/usr/bin/env python3
"""Apply the H7000 overlay to an XiKoTaSu/android_kernel_qcom_sdm660 checkout.

Idempotent: running it twice changes nothing.

  python3 tools/apply_overlay.py [--root .] [--touch] [--no-backlight]

It performs:
  1. drivers/video/backlight/ktz8864.c              (new file)
  2. drivers/video/backlight/Kconfig                (add BACKLIGHT_KTZ8864)
  3. drivers/video/backlight/Makefile               (add obj-$(CONFIG_BACKLIGHT_KTZ8864))
  4. arch/arm64/configs/vendor/sdm660-perf_defconfig (add the Kconfig switches)
  5. sanity checks on the device tree plumbing
"""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OVERLAY = os.path.join(os.path.dirname(HERE), "overlay")

KCONFIG_TEXT = """
config BACKLIGHT_KTZ8864
	tristate "KTZ8864 backlight controller"
	depends on BACKLIGHT_CLASS_DEVICE
	depends on I2C
	help
	  Say Y here to take the KTZ8864 backlight controller out of reset and
	  program its enable registers.  Brightness itself is driven through
	  the PM660L PWM by the MDSS panel code (bl_ctrl_pwm).

	  This is needed on the EEBBK S5 (H7000).
"""

DEFCONFIG_LINES = [
    # KTZ8864 backlight (H7000 面板 bl_ctrl_pwm 需要它把芯片使能起来)
    "CONFIG_BACKLIGHT_KTZ8864=y",
    # Android 11 vendor 需要的、4.4 工作配置里有但 4.19 defconfig 漏掉的项
    "CONFIG_SYNC_FILE=y",
    "CONFIG_SW_SYNC=y",
    "CONFIG_TMPFS_XATTR=y",
    "CONFIG_CRYPTO_XTS=y",
    'CONFIG_ANDROID_BINDER_DEVICES="binder,hwbinder,vndbinder"',
]

TOUCH_LINES = [
    "CONFIG_DRM_PANEL=y",
    "CONFIG_TOUCHSCREEN_FTS=y",
]


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def patch_kconfig(root):
    path = os.path.join(root, "drivers/video/backlight/Kconfig")
    text = read(path)
    if "config BACKLIGHT_KTZ8864" in text:
        print("  Kconfig: already present")
        return
    lines = text.splitlines(keepends=True)
    idx = None
    for i in range(len(lines) - 1, -1, -1):
        # the file ends with "endif # BACKLIGHT_CLASS_DEVICE" /
        # "endif # BACKLIGHT_LCD_SUPPORT"; put our entry inside the
        # "if BACKLIGHT_LCD_SUPPORT" block, i.e. before the last endif.
        if lines[i].strip().startswith("endif"):
            idx = i
            break
    if idx is None:
        lines.append(KCONFIG_TEXT)
    else:
        lines.insert(idx, KCONFIG_TEXT)
    write(path, "".join(lines))
    print("  Kconfig: inserted BACKLIGHT_KTZ8864")


def patch_makefile(root):
    path = os.path.join(root, "drivers/video/backlight/Makefile")
    text = read(path)
    if "CONFIG_BACKLIGHT_KTZ8864" in text:
        print("  Makefile: already present")
        return
    if not text.endswith("\n"):
        text += "\n"
    text += "obj-$(CONFIG_BACKLIGHT_KTZ8864)\t+= ktz8864.o\n"
    write(path, text)
    print("  Makefile: added ktz8864.o")


def patch_defconfig(root, lines):
    path = os.path.join(root, "arch/arm64/configs/vendor/sdm660-perf_defconfig")
    text = read(path)
    added = []
    for line in lines:
        key = line.split("=")[0]
        present = any(l.split("=")[0].strip() == key for l in text.splitlines())
        if not present:
            text += line + "\n"
            added.append(line)
    if added:
        write(path, text)
        print("  defconfig: added %s" % ", ".join(added))
    else:
        print("  defconfig: nothing to add")


def check_device_tree(root):
    ok = True
    dts_dir = os.path.join(root, "arch/arm64/boot/dts/vendor/qcom/eebbk")
    if not os.path.isdir(dts_dir):
        print("  !! missing %s" % dts_dir)
        ok = False
    qcom_mk = os.path.join(root, "arch/arm64/boot/dts/vendor/qcom/Makefile")
    if os.path.exists(qcom_mk) and "sda660-mtp-H7000.dtb" not in read(qcom_mk):
        print("  !! sda660-mtp-H7000.dtb is not in the qcom dts Makefile")
        ok = False
    ov = os.path.join(dts_dir, "sda660-mtp-H7000-overlay.dtsi")
    if os.path.exists(ov) and "ktz8864" not in read(ov):
        print("  !! overlay does not reference ktz8864 any more")
        ok = False
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--touch", action="store_true",
                    help="also enable focaltech touch (needs CONFIG_DRM_PANEL)")
    ap.add_argument("--no-backlight", action="store_true")
    args = ap.parse_args()
    root = os.path.abspath(args.root)

    print("overlay -> %s" % root)
    if not args.no_backlight:
        src = os.path.join(OVERLAY, "ktz8864.c")
        dst = os.path.join(root, "drivers/video/backlight/ktz8864.c")
        shutil.copyfile(src, dst)
        print("  copied drivers/video/backlight/ktz8864.c")
        patch_kconfig(root)
        patch_makefile(root)
        patch_defconfig(root, DEFCONFIG_LINES)
    if args.touch:
        patch_defconfig(root, TOUCH_LINES)

    print("device tree checks:")
    ok = check_device_tree(root)
    print("done%s" % ("" if ok else " (with warnings)"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
