# Olmec

Interactive Olmec head sculpture from *Legends of the Hidden Temple*, originally built for Bay to Breakers 2026.

A Raspberry Pi inside a foam sculpture asks trivia questions to passersby, judges their answers, and rewards correct ones with a jello shot. AI-generated voice (ElevenLabs), pulsing red LED eyes synced to speech, control via phone or four physical buttons.

---

## Table of Contents

1. [How to operate it](#how-to-operate-it)
2. [Connecting to the Pi at an event](#connecting-to-the-pi-at-an-event)
3. [Connecting the Pi to home WiFi](#connecting-the-pi-to-home-wifi)
4. [Service management on the Pi](#service-management-on-the-pi)
5. [Adding or changing content](#adding-or-changing-content)
6. [Regenerating audio](#regenerating-audio)
7. [Pulling updates onto the Pi](#pulling-updates-onto-the-pi)
8. [Hardware](#hardware)
9. [Troubleshooting](#troubleshooting)

---

## How to operate it

### Quick operating guide

Olmec has two modes: **WANDERING** (calling out to the crowd) and **QUIZ** (asking trivia).

**Physical buttons** (bottom-right corner of the Pi header):
| Button | Action |
|---|---|
| Next Question | Switch to QUIZ mode and ask a random trivia question |
| Correct | Play a "correct!" response |
| Incorrect | Play an "incorrect" response (followed by the reveal of the right answer if there was an active question) |
| Say Something | Play a random WANDERING clip (works regardless of mode) |

All four buttons work without any phone connected — the Pi can run completely standalone.

**Phone UI** (richer controls):
- Connect your phone to the Pi (see below), open `http://olmec.local:8000/olmec/`
- Tap the **CONTROLS** button in the top-right to slide in the operator panel
- Mode toggle, difficulty slider, "jello shots available" toggle, soundboard, etc.

The operator's UI also shows what the next correct answer is once a question has been asked, so you (or whoever's holding the phone) can decide if the person got it right.

---

## Connecting to the Pi at an event

The Pi runs its own WiFi network ("Olmec") when away from home. Your phone or laptop joins it like any other network.

**Default WiFi:**
- SSID: `Olmec`
- Password: `olmecolmec`

Once connected, open:
- **http://olmec.local:8000/olmec/** — main UI (Olmec face + slide-out operator panel)

(If `olmec.local` doesn't resolve on your device, use `http://10.42.0.1:8000/olmec/` instead — that's the Pi's IP in AP mode.)

You can SSH in from your phone too — connect to the "Olmec" network, then in Termius / Termux:
```
ssh matt@olmec.local
```

---

## Connecting the Pi to home WiFi

The Pi defaults to **AP mode** so it always works at events. To temporarily use a home WiFi (for example, to pull updates from GitHub or generate audio with ElevenLabs from the Pi), you switch the active connection.

**1. SSH into the Pi from your laptop**
- Connect your laptop to the "Olmec" WiFi
- `ssh matt@olmec.local`

**2. List saved networks**
```bash
nmcli connection show
```

You'll see something like `olmec-ap`, `headquarters_5G`, etc.

**3. Add your home network if it's not there**
```bash
sudo nmcli device wifi connect "YOUR_SSID" password "YOUR_PASSWORD"
```

**4. Switch to home WiFi**
```bash
sudo nmcli connection down olmec-ap
sudo nmcli connection up YOUR_SSID
```

The Pi loses the "Olmec" AP and joins your network. You can now SSH to it from your home WiFi (`ssh matt@olmec.local`) and the Pi has internet.

**5. Switch back to AP mode**
```bash
sudo nmcli connection up olmec-ap
```

The home WiFi connection drops and the AP comes back. Reboot the Pi and the AP comes up automatically (it's the highest-priority autoconnect).

---

## Service management on the Pi

The Olmec server runs as a systemd service called `olmec`. It auto-starts on boot.

```bash
sudo systemctl status olmec          # check it's running
sudo systemctl restart olmec         # apply code changes
sudo systemctl stop olmec            # stop temporarily
sudo systemctl start olmec           # start again
journalctl -u olmec -f               # tail the live log (Ctrl-C to exit)
journalctl -u olmec -n 100           # last 100 log lines
```

---

## Adding or changing content

All content lives in YAML files under `data/content/` — these are the source of truth. After editing, regenerate audio (next section) and re-seed the DB.

| File | Contents |
|---|---|
| `wandering.yaml` | Barker / walkaround clips. Played by the **Say Something** button and the wandering soundboard. |
| `canned.yaml` | Iconic phrases for the soundboard only — not in any random rotation. |
| `questions.yaml` | Trivia questions with answers and accepted variants. |
| `responses.yaml` | Correct/incorrect/no-jello-correct response lines. |

**Add a wandering clip:**
```yaml
- id: my_new_clip
  text: "Step right up to the temple!"
  tags: [barker]
```

**Add a question:**
```yaml
- id: largest_planet
  question_text: "What is the largest planet in our solar system?"
  answer: "Jupiter"
  accept: ["jupiter"]
  category: science
  difficulty: 2
```

The `id` becomes the audio filename. The `accept` list controls fuzzy matching for STT answer recognition — include common variants.

**Multiple takes** of the same line (for variety):
```yaml
- id: correct_well_done
  text: "That is correct!"
  takes: 3   # generates 3 audio files with different deliveries
```

The runtime picks a random take each time. ElevenLabs charges per character, so each take costs another API call.

---

## Regenerating audio

Audio clips are generated from YAML on a Mac (or anywhere with internet + ElevenLabs API key). They are then committed to the repo so the Pi just consumes pre-baked WAV files.

**One-time setup (Mac):**
- `cp .env.example .env`
- Add your `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` to `.env`
- `uv sync --extra pipeline` — installs ElevenLabs + audio effects deps

**Generate any missing clips:**
```bash
uv run python pipeline/generate_audio.py
```

The script reads from YAML, generates only the files that don't exist yet, and writes them to `data/audio/olmec-v1/`. To preview first without API calls:
```bash
uv run python pipeline/generate_audio.py --dry-run
```

**Restrict to one category:**
```bash
uv run python pipeline/generate_audio.py --category wandering
```

**Force regeneration of existing clips** (e.g., after changing a clip's text):
```bash
# delete the old WAV files first, OR pass --regenerate-all
uv run python pipeline/generate_audio.py --regenerate-all
```

**Apply reverb + loudness effects:**
After generating, run the effects pipeline. This reads from `data/audio/olmec-v1/` (dry) and writes to `data/audio/olmec-v1-fx/` (wet — this is what the Pi actually plays).
```bash
uv run python pipeline/apply_effects.py --voice-name olmec-v1
```

Or just the new ones, all categories:
```bash
uv run python pipeline/apply_effects.py --voice-name olmec-v1 --category wandering
```

**Re-seed the SQLite database** so the runtime knows about the new entries:
```bash
uv run python pipeline/seed_db.py
```

**Full workflow for one new clip:**
```bash
# 1. Edit data/content/wandering.yaml — add the entry
# 2. Generate audio + effects + DB
uv run python pipeline/generate_audio.py --category wandering
uv run python pipeline/apply_effects.py --voice-name olmec-v1 --category wandering
uv run python pipeline/seed_db.py
# 3. Commit
git add -A && git commit -m "Add new wandering clip" && git push
```

---

## Pulling updates onto the Pi

Once you've pushed changes (new YAML, audio, or code), pull them on the Pi:

**1. Switch the Pi to a network with internet** (see "Connecting the Pi to home WiFi" above)

**2. Pull and restart:**
```bash
cd ~/code/olmec
git pull
uv run python pipeline/seed_db.py    # re-seed if YAML changed
sudo systemctl restart olmec
```

**3. Switch back to AP mode for the event:**
```bash
sudo nmcli connection up olmec-ap
```

---

## Hardware

Everything lives inside (or attached to) a foam Olmec head sculpture.

- Raspberry Pi 5 (4GB)
- USB-C PD power bank (20,000mAh+, supports 5V/5A or 5V/3A with `usb_max_current_enable=1`)
- Portable speaker (3.5mm into the Pi, has its own battery)
- USB cardioid microphone
- 80x WS2812B addressable LEDs (40 per eye)
  - Data line: GPIO 10 (SPI0 MOSI, physical pin 19) through a 330Ω resistor
  - 5V power from a separate buck converter (not the Pi's 5V rail), common ground
- 4x momentary tactile buttons on GPIOs 16/26/20/21 (pins 36/37/38/40), all sharing GND on pin 39

See `hardware/setup.md` for full Pi OS setup and `hardware/olmec.service` for the systemd unit.

---

## Troubleshooting

**"Olmec isn't playing audio when I press a button."**
- Check the service is running: `sudo systemctl status olmec`
- Check logs: `journalctl -u olmec -n 50`
- Confirm the audio device: `aplay -l` should list your speaker

**"The LEDs aren't lighting up."**
- Check `journalctl -u olmec | grep -i neopixel` — you should see `NeoPixel SPI initialized (80 LEDs)`
- Confirm SPI is enabled in `sudo raspi-config` → Interface Options → SPI
- Verify the data wire is solid (especially during jiggling — flickers green = signal integrity issue, may need a level shifter or in-line 1N4001 diode on the strip's 5V)
- Use the LED test page: `http://olmec.local:8000/leds/`

**"My phone shows 'no internet' on the Olmec WiFi."**
That's expected — there's no upstream internet on the Pi's AP. Dismiss the warning; the local connection still works.

**"`olmec.local` doesn't resolve."**
- Try the static IP: `http://10.42.0.1:8000/olmec/`
- On some Androids, mDNS is flaky over the AP — use the IP

**"The buttons don't work."**
- Check `journalctl -u olmec | grep -i button` — you should see registration log lines for each button on its GPIO pin
- If you see `gpiozero not available`, run `uv sync --extra stt --extra pi` on the Pi

**Volume is too low / too high:**
- SSH in, run `alsamixer` to adjust
- Press F6 to switch sound cards, arrows to adjust, M to mute, Esc to save
- `sudo alsactl store` to persist across reboots
