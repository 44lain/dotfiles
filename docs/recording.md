# Recording and replay clips

`rec` (`~/.local/bin/rec`) wraps [gpu-screen-recorder](https://git.dec05eba.com/gpu-screen-recorder/about/).
The GPU does the encoding (NVENC on NVIDIA, VAAPI on AMD/Intel), so the CPU cost is near zero,
which matters next to a CPU-bound game.

| Command | Key | What it does |
| --- | --- | --- |
| `rec replay` | started at login on `desktop` (`autostart` in `hosts.toml`) | keeps the last 60 s in RAM |
| `rec clip` | `SUPER+CTRL+R` | saves those 60 s to `~/Vídeos/clips` |
| `rec toggle` | `SUPER+CTRL+SHIFT+R` | starts / stops a full recording |
| `rec status`, `rec stop` | | what is running; stop everything |

It captures the focused monitor at 60 fps, game audio only (the microphone is not recorded).
Knobs, as environment variables: `REC_DIR`, `REC_SECONDS`, `REC_FPS`, `REC_QUALITY`
(`medium` | `high` | `very_high` | `ultra`), `REC_AUDIO` (`"default_output|default_input"` mixes the mic in).

Install: `gpu-screen-recorder` is in the Fedora COPR `brycensranch/gpu-screen-recorder-git`,
in the AUR, and on Flathub. It is not in `packages.toml`, so `rice doctor` does not check for it.

## A short GIF for the README

```bash
rec toggle                      # start, do the thing, then:
rec toggle                      # stop
ffmpeg -ss 0.5 -t 6 -i clip.mp4 -vf "fps=15,scale=960:-1" -c:v libwebp -loop 0 -q:v 70 out.webp
```
