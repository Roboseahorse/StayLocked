# StayLocked

**[⬇ Download StayLocked.exe](https://github.com/Roboseahorse/StayLocked/releases/latest/download/StayLocked.exe)** ready to run, no install needed

Free open-source focus tool that locks your computer to only the applications you allow.

Inspired by Cold Turkey Micromanager. Whitelist the apps you need — everything else is blocked.

---

## Features

- Unlimited application allowlist + **named profiles**
- Timed sessions, “until restart”, Pomodoro, or allowance modes
- **+10 min extend** button during timed blocks
- Force-close or minimise non-whitelisted apps
- Optional Task Manager / Process Explorer protection
- Emergency stop with password + confirmation phrase
- Session resume if the app is closed mid-session
- Completely free, no accounts, no tracking

  <img width="364" height="489" alt="Screenshot 2026-11-07 111409" src="https://github.com/user-attachments/assets/04fa994d-567e-4b32-b562-36f17356dc05" />

---

## How to use

1. Download `StayLocked.exe` from the link above
2. Run it
3. Add the apps you need to the Allowlist
4. Choose a mode and click **Start Focus Block**

---

## Why StayLocked?

Most distraction blockers let you blacklist sites or apps. StayLocked does the opposite — it only lets through the programs you explicitly allow. This creates a much stricter environment that is harder to rationalise your way out of.

- Unlimited application allowlist + **named profiles**
- Timed sessions, “until restart”, Pomodoro cycles, or allowance-then-block modes
- **+10 min extend** button during timed blocks
- Force-close or minimise non-whitelisted apps
- Optional aggressive Task Manager / Process Explorer blocking
- Optional emergency password + confirmation phrase to exit early
- Session resume if the app is closed or updated mid-session
- Completely free, no accounts, no tracking, no paywalls

---

## Project Structure

```
StayLocked/
├── __init__.py
├── __main__.py          # python -m StayLocked
├── app.py               # Main CustomTkinter UI
├── config.py            # Paths, defaults, load/save
├── session.py           # Active session persistence & resume
├── allowlist.py         # Allowlist + profiles
├── enforcer.py          # Process scanning & force-close/minimize
├── modes.py             # Timed / Restart / Pomodoro / Allowance runners
├── emergency.py         # High-friction emergency stop dialog
├── updater.py           # GitHub Releases auto-update
└── platform/
    ├── windows.py       # win32 helpers
    ├── macos.py         # stubs
    └── linux.py         # stubs
```
---

## How a Session Works

1. Add the applications you need to the Allowlist tab (or load a Profile).
2. Choose your preferred mode and duration on the Duration tab.
3. Review settings and click **Start Focus Block**.
4. Only allowlisted apps remain usable until the session ends (or you complete the emergency stop process).

While a block is active the main window cannot be closed normally. The Emergency Stop button requires deliberate, multi-step confirmation so that quitting early is not a casual decision.

During a timed block you can click **+10 min** to extend the session without stopping.

---

## Privacy

StayLocked stores everything locally in `~/.StayLocked/` (or the equivalent on Windows).

No telemetry, no accounts, no cloud services.

---

## Limitations

StayLocked is a user-space application. A determined user can still terminate the process through Task Manager (unless the aggressive protection option is enabled). It is designed to create strong friction against casual distraction, not to provide kernel-level lockdown.

Future improvements (watchdog process, stronger process protection, system tray, scheduling, statistics) are planned on top of this modular base.

---

## License

MIT License — free to use, modify, and distribute.
