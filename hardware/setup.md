# Raspberry Pi Setup

## 1. First-time setup

After flashing Raspberry Pi OS and connecting to WiFi:

```bash
# System deps for audio
sudo apt update && sudo apt install -y libportaudio2 libsndfile1 git

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# Clone the repo
git clone https://github.com/<your-user>/olmec.git ~/code/olmec
cd ~/code/olmec

# Install Python deps with STT support
uv sync --extra stt

# Seed the question database
uv run python pipeline/seed_db.py

# Create your .env from the example and edit OLMEC_MODE=pi etc.
cp .env.example .env
nano .env
```

## 2. Pick the right audio devices

Plug in your USB mic and speaker, then run:

```bash
uv run python -c "import sounddevice; print(sounddevice.query_devices())"
```

You'll see something like:
```
  0 USB PnP Sound Device, ALSA (1 in, 0 out)
  1 USB Audio Device, ALSA (0 in, 2 out)
* 2 bcm2835 Headphones, ALSA (0 in, 8 out)
```

Pick the substring that uniquely identifies each:
- For the mic: `USB PnP` (or whatever's unique)
- For the speaker: `USB Audio` (or whatever's unique)

Edit `.env`:
```
OLMEC_AUDIO_INPUT_DEVICE=USB PnP
OLMEC_AUDIO_OUTPUT_DEVICE=USB Audio
```

This pins the device by name, so it won't break if USB ports get re-enumerated on reboot.

## 3. Auto-start on boot via systemd

Copy the service file and enable it:

```bash
sudo cp ~/code/olmec/hardware/olmec.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable olmec
sudo systemctl start olmec
```

Verify it's running:
```bash
sudo systemctl status olmec
```

View logs:
```bash
journalctl -u olmec -f
```

Stop / restart:
```bash
sudo systemctl stop olmec
sudo systemctl restart olmec
```

If you edit the service file, run `sudo systemctl daemon-reload && sudo systemctl restart olmec`.

## 4. Verify

After reboot:
1. Wait ~30 seconds for the Pi to come up and the service to start
2. From your phone (same WiFi): http://olmec.local:8000/olmec/
3. Press a soundboard button to test the speaker
4. Switch to QUIZ mode and try a trivia question to test the mic

If something doesn't work, check `journalctl -u olmec -n 100`.
