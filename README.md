 Here's your complete README content. Just copy and paste it into a file named `README.md` inside your bot folder.

---

```markdown
# 👑 Baron D Forex

**A Claude Code-style terminal trading engine for MetaTrader 5**

Type `aron` and watch the crown chase wealth around the globe before the trading engine takes over your terminal.

---

## 🚀 Quick Start

### 1. Prerequisites

- **Windows** (CMD/PowerShell)
- **Python 3.8+**
- **MetaTrader 5** installed and running
- A **Deriv** or **MT5-compatible** broker account

### 2. Install Dependencies

```bash
pip install MetaTrader5 pandas rich
```

> The bot auto-installs `rich` if missing, but manual install is recommended.

### 3. Set Up the `aron` Command

Save the following as **`aron.bat`** in a folder in your system PATH (e.g., `C:\Tools` or `C:\Windows\System32`):

```batch
@echo off
cd /d "%USERPROFILE%\Documents\bot"
python baron.py
pause
```

**Add `C:\Tools` to your PATH:**
1. Press `Win + S`, search **"Environment Variables"**
2. Click **"Edit the system environment variables"**
3. Click **"Environment Variables"**
4. Under **User variables**, find `Path` → **Edit** → **New** → type `C:\Tools` → OK

### 4. Launch

Open a **new** CMD window and type:

```bash
aron
```

---

## 🎨 Features

| Feature | Description |
|---------|-------------|
| **👑 Splash Animation** | Crown and dollar sign orbit a spinning globe on startup |
| **🖥️ Claude Code UI** | Rich terminal dashboard with live panels and rounded borders |
| **📊 Live Dashboard** | Real-time balance, equity, margin, and P/L |
| **📈 Position Table** | Color-coded active trades with entry, SL, TP, and profit |
| **🔮 Market Analysis** | Multi-timeframe BOS + FVG analysis with confidence scores |
| **🛡️ Risk Management** | 1% risk per trade, daily loss limits, trailing stops |
| **⚡ Auto-Scaling** | Switches to scalping mode for accounts under $100 |
| **🔐 Passkey Lock** | System-bound authentication to protect your bot |

---

## ⚙️ Configuration

Edit the constants at the top of `baron.py`:

```python
# Symbols to trade
SYMBOLS = ["Volatility 50 (1s) Index"]

# Risk per trade (1%)
RISK_PER_TRADE = 0.01

# Daily limits
DAILY_PROFIT_TARGET = 500.0
DAILY_LOSS_LIMIT = -100.0

# Reward:Risk ratios
MIN_R_RATIO = 2.0
TARGET_R_RATIO = 3.0

# Position limits
MAX_POSITIONS_PER_SYMBOL = 2
MAX_SPREAD_POINTS = 40000
```

### Strategy Modes

| Account Balance | Strategy | Timeframes | Risk/Trade |
|-----------------|----------|------------|------------|
| **≥ $100** | Standard (TTrades) | H1, M15, M5 | 1.0% |
| **< $100** | Scalping | M5, M1 | 0.5% |

---

## 🧠 Trading Logic

The bot follows a **Smart Money Concepts (SMC)** approach:

1. **Market Structure** — Identifies swing highs/lows and Breaks of Structure (BOS)
2. **Fair Value Gaps** — Detects FVGs on M15/M5/M1 for entry zones
3. **Multi-Timeframe** — H1 for trend bias, M15/M5 for execution
4. **Risk Management** — Position sizing based on account balance and SL distance
5. **Trade Management** — Trailing stops, partial closes at 1R/2R, full close at 3R

---

## 🖥️ UI Layout

```
┌─────────────────────────────────────────────────────────────┐
│  👑 BARON D FOREX 💲    Balance: $1,250.00    Status: LIVE  │
├──────────────┬──────────────────────┬───────────────────────┤
│   ACCOUNT    │     POSITIONS        │      ANALYSIS         │
│  Balance     │  Symbol  Type  P/L   │  V50(1s) BUY 70%      │
│  Equity      │  V50(1s) BUY  +$12   │  Entry: 847320.50     │
│  Margin      │                      │  SL: 847300.00        │
│  Leverage    │                      │  TP: 847380.00        │
├──────────────┴──────────────────────┴───────────────────────┤
│  📝 Recent Events                                           │
│  14:32:05 | Trade executed: V50(1s) BUY 0.003 @ 847320.50 │
│  14:31:45 | SL modified for position 123456789 to 847300  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔐 Security

The bot uses a **system-bound passkey** stored in `bot_access.json`:

- Passkey: `1234567890#12345678901#`
- Locked to your machine ID (`hostname + OS + version`)
- Only needs to be entered once per machine

To reset access, delete `bot_access.json` and re-launch.

---

## 📁 File Structure

```
📂 Documents/
└── 📂 bot/
    ├── 📄 baron.py              # Main trading engine
    ├── 📄 aron.bat              # Launcher script (store in PATH)
    ├── 📄 bot_access.json       # Auth cache (auto-generated)
    └── 📄 README.md             # This file
```

---

## ⚠️ Risk Disclaimer

**Trading involves substantial risk of loss.** This bot is for educational purposes. Always:

- Test on a **demo account** first
- Never risk more than you can afford to lose
- Monitor the bot during high-volatility events
- Keep MetaTrader 5 running while the bot is active

---

## 🛠️ Troubleshooting

| Issue | Solution |
|-------|----------|
| `MT5 initialize failed` | Ensure MetaTrader 5 is open and logged in |
| `Symbol not found` | Check that the symbol exists in your broker's Market Watch |
| `Trade failed: 10014` | Invalid stops — increase SL distance from entry |
| `aron` not recognized | Ensure `aron.bat` is in a folder in your system PATH |
| UI looks broken | Resize terminal to at least **120×30** characters |

---

## 📝 Changelog

| Version | Date | Changes |
|---------|------|---------|
| 2.0 | 2026-08-30 | Claude Code UI, animated splash, Rich dashboard |
| 1.0 | 2026-08-25 | Initial TTrades SMC strategy engine |

---

## 👤 Author

**Baron D** — *The Crown Chases Wealth*

---

**Trade smart. Risk small. Let the crown run.**
```

---

Copy the block above, paste it into Notepad, save as `README.md` in your `Documents\bot` folder, and you're set.
