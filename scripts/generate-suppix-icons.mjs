#!/usr/bin/env node
/**
 * Regenerate all raster icons from branding/suppix-ai-mark.svg (SUPPIX AI mark).
 * Run: node scripts/generate-suppix-icons.mjs
 */
import { execSync } from "child_process";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const svg = path.join(root, "branding", "suppix-ai-mark.svg");

if (!fs.existsSync(svg)) {
  console.error("Missing", svg);
  process.exit(1);
}

function render(outRel, size) {
  const out = path.join(root, outRel);
  fs.mkdirSync(path.dirname(out), { recursive: true });
  execSync(
    `npx --yes @resvg/resvg-js-cli --fit-width ${size} "${svg}" "${out}"`,
    { stdio: "inherit", cwd: root },
  );
  console.log("wrote", outRel, size);
}

const jobs = [
  ["branding/suppix-icon-192.png", 192],
  ["branding/suppix-icon-512.png", 512],
  ["mobile/web/favicon.png", 48],
  ["mobile/web/icons/Icon-192.png", 192],
  ["mobile/web/icons/Icon-512.png", 512],
  ["mobile/web/icons/Icon-maskable-192.png", 192],
  ["mobile/web/icons/Icon-maskable-512.png", 512],
  ["mobile/android/app/src/main/res/mipmap-mdpi/ic_launcher.png", 48],
  ["mobile/android/app/src/main/res/mipmap-mdpi/ic_launcher_round.png", 48],
  ["mobile/android/app/src/main/res/mipmap-hdpi/ic_launcher.png", 72],
  ["mobile/android/app/src/main/res/mipmap-hdpi/ic_launcher_round.png", 72],
  ["mobile/android/app/src/main/res/mipmap-xhdpi/ic_launcher.png", 96],
  ["mobile/android/app/src/main/res/mipmap-xhdpi/ic_launcher_round.png", 96],
  ["mobile/android/app/src/main/res/mipmap-xxhdpi/ic_launcher.png", 144],
  ["mobile/android/app/src/main/res/mipmap-xxhdpi/ic_launcher_round.png", 144],
  ["mobile/android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png", 192],
  ["mobile/android/app/src/main/res/mipmap-xxxhdpi/ic_launcher_round.png", 192],
  ["mobile/macos/Runner/Assets.xcassets/AppIcon.appiconset/app_icon_16.png", 16],
  ["mobile/macos/Runner/Assets.xcassets/AppIcon.appiconset/app_icon_32.png", 32],
  ["mobile/macos/Runner/Assets.xcassets/AppIcon.appiconset/app_icon_64.png", 64],
  ["mobile/macos/Runner/Assets.xcassets/AppIcon.appiconset/app_icon_128.png", 128],
  ["mobile/macos/Runner/Assets.xcassets/AppIcon.appiconset/app_icon_256.png", 256],
  ["mobile/macos/Runner/Assets.xcassets/AppIcon.appiconset/app_icon_512.png", 512],
  ["mobile/macos/Runner/Assets.xcassets/AppIcon.appiconset/app_icon_1024.png", 1024],
  ["mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-20x20@1x.png", 20],
  ["mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-20x20@2x.png", 40],
  ["mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-20x20@3x.png", 60],
  ["mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-29x29@1x.png", 29],
  ["mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-29x29@2x.png", 58],
  ["mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-29x29@3x.png", 87],
  ["mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-40x40@1x.png", 40],
  ["mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-40x40@2x.png", 80],
  ["mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-40x40@3x.png", 120],
  ["mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-60x60@2x.png", 120],
  ["mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-60x60@3x.png", 180],
  ["mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-76x76@1x.png", 76],
  ["mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-76x76@2x.png", 152],
  ["mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-83.5x83.5@2x.png", 167],
  ["mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-1024x1024@1x.png", 1024],
];

for (const [rel, size] of jobs) {
  render(rel, size);
}

console.log("Done — all icons from suppix-ai-mark.svg");
