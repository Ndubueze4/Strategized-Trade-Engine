import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import time
import platform
import os
import json
import logging
import math
from typing import Dict, List, Tuple, Optional, Any

# ----------------- CONFIG -----------------
SYMBOLS = ["Volatility 50 (1s) Index"]

# Timeframes
TIMEFRAME_1M = mt5.TIMEFRAME_M1
TIMEFRAME_5M = mt5.TIMEFRAME_M5
TIMEFRAME_15M = mt5.TIMEFRAME_M15
TIMEFRAME_30M = mt5.TIMEFRAME_M30
TIMEFRAME_1H = mt5.TIMEFRAME_H1

# --- RISK CONFIG ---
RISK_PER_TRADE = 0.01  # 1% risk per trade
MAX_RISK_PER_DAY = 0.03  # 3% max daily drawdown
MIN_R_RATIO = 2.0  # Minimum reward:risk ratio
TARGET_R_RATIO = 3.0  # Target reward:risk ratio

# --- TRADE CONFIG ---
MIN_LOT = 0.0003
MAX_LOT = 2.0
MAGIC_BASE = 500000
MAX_POSITIONS_PER_SYMBOL = 2
MAX_SPREAD_POINTS = 40000

# --- TIMING ---
SLEEP_INTERVAL = 1.0
COOLDOWN_SECONDS = 30

# --- PROFIT MANAGEMENT ---
DAILY_PROFIT_TARGET = 500.0
DAILY_LOSS_LIMIT = -100.0
TRAILING_START_PERCENT = 0.5  # Start trailing at 50% of TP
TRAILING_STEP = 0.25  # Move SL every 25% of remaining distance

# --- SCALING (TTrades Style) ---
SCALING_RISK_PER_TRADE = 0.005  # 0.5% per scaling trade
SCALING_MAX_TRADES = 3
SCALING_TARGET_R = 1.5  # Lower R:R for scalping

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TTradesBot")

# ----------------- MARKET STRUCTURE CLASS -----------------
class MarketStructure:
    """Analyzes market structure for swing points and breaks of structure."""
    
    def __init__(self, symbol: str, timeframe: int, lookback: int = 50):
        self.symbol = symbol
        self.timeframe = timeframe
        self.lookback = lookback
        
    def get_rates(self) -> Optional[pd.DataFrame]:
        """Get OHLCV data."""
        rates = mt5.copy_rates_from_pos(self.symbol, self.timeframe, 0, self.lookback)
        if rates is None or len(rates) < 10:
            return None
        return pd.DataFrame(rates)
    
    def get_swing_highs(self, df: pd.DataFrame, strength: int = 2) -> List[float]:
        """Find swing highs with specified strength."""
        highs = []
        for i in range(strength, len(df) - strength):
            if all(df['high'].iloc[i] > df['high'].iloc[i-j] for j in range(1, strength+1)) and \
               all(df['high'].iloc[i] > df['high'].iloc[i+j] for j in range(1, strength+1)):
                highs.append(df['high'].iloc[i])
        return highs
    
    def get_swing_lows(self, df: pd.DataFrame, strength: int = 2) -> List[float]:
        """Find swing lows with specified strength."""
        lows = []
        for i in range(strength, len(df) - strength):
            if all(df['low'].iloc[i] < df['low'].iloc[i-j] for j in range(1, strength+1)) and \
               all(df['low'].iloc[i] < df['low'].iloc[i+j] for j in range(1, strength+1)):
                lows.append(df['low'].iloc[i])
        return lows
    
    def get_break_of_structure(self) -> Dict[str, Any]:
        """Detect if we're having a break of structure (BOS)."""
        df = self.get_rates()
        if df is None:
            return {"bos": "NONE", "direction": "NEUTRAL"}
        
        # Check for market structure shift
        swing_highs = self.get_swing_highs(df, 2)
        swing_lows = self.get_swing_lows(df, 2)
        
        if not swing_highs or not swing_lows:
            return {"bos": "NONE", "direction": "NEUTRAL"}
        
        last_swing_high = swing_highs[-1] if swing_highs else None
        last_swing_low = swing_lows[-1] if swing_lows else None
        current_price = df['close'].iloc[-1]
        
        # Bullish BOS: price breaks above last swing high
        if last_swing_high and current_price > last_swing_high:
            return {"bos": "BULLISH", "direction": "UP", "level": last_swing_high}
        
        # Bearish BOS: price breaks below last swing low
        if last_swing_low and current_price < last_swing_low:
            return {"bos": "BEARISH", "direction": "DOWN", "level": last_swing_low}
        
        return {"bos": "NONE", "direction": "NEUTRAL"}

# ----------------- FVG DETECTION -----------------
class FairValueGap:
    """Detects Fair Value Gaps (FVG) on any timeframe."""
    
    def __init__(self, symbol: str, timeframe: int):
        self.symbol = symbol
        self.timeframe = timeframe
    
    def get_fvg(self) -> List[Dict[str, Any]]:
        """Find all FVGs in the recent candles."""
        rates = mt5.copy_rates_from_pos(self.symbol, self.timeframe, 0, 20)
        if rates is None or len(rates) < 4:
            return []
        
        fvgs = []
        df = pd.DataFrame(rates)
        
        for i in range(2, len(df)):
            # Bullish FVG: gap between candle high and next candle low
            if df['low'].iloc[i] > df['high'].iloc[i-2]:
                fvgs.append({
                    "type": "BULLISH",
                    "top": df['low'].iloc[i],
                    "bottom": df['high'].iloc[i-2],
                    "mid": (df['low'].iloc[i] + df['high'].iloc[i-2]) / 2
                })
            
            # Bearish FVG: gap between candle low and next candle high
            if df['high'].iloc[i] < df['low'].iloc[i-2]:
                fvgs.append({
                    "type": "BEARISH",
                    "top": df['low'].iloc[i-2],
                    "bottom": df['high'].iloc[i],
                    "mid": (df['low'].iloc[i-2] + df['high'].iloc[i]) / 2
                })
        
        return fvgs

# ----------------- RISK MANAGER -----------------
class RiskManager:
    """Handles all position sizing and risk calculations."""
    
    def __init__(self, risk_per_trade: float = 0.01):
        self.risk_per_trade = risk_per_trade
        self.daily_loss_limit = -100.0
        self.daily_win_limit = 500.0
    
    def calculate_position_size(self, symbol: str, entry: float, stop_loss: float) -> float:
        """
        Calculate position size based on risk per trade.
        Uses account balance, not equity, for consistent risk.
        """
        account = mt5.account_info()
        if account is None:
            return MIN_LOT
        
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return MIN_LOT
        
        # Calculate risk amount in currency
        risk_amount = account.balance * self.risk_per_trade
        
        # Calculate distance to stop loss
        sl_distance = abs(entry - stop_loss)
        if sl_distance <= 0:
            return MIN_LOT
        
        # Get tick value
        tick_value = symbol_info.trade_tick_value
        tick_size = symbol_info.trade_tick_size
        
        # Calculate lot size
        # lot = risk_amount / (sl_distance / tick_size * tick_value)
        lot = risk_amount / (sl_distance * tick_value / tick_size)
        
        # Round to valid lot size
        lot = self._sanitize_volume(symbol, lot)
        
        return max(lot, MIN_LOT)
    
    def _sanitize_volume(self, symbol: str, requested_lots: float) -> float:
        """Adjust lot size to broker constraints."""
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return requested_lots
        
        min_vol = symbol_info.volume_min
        max_vol = symbol_info.volume_max
        vol_step = symbol_info.volume_step
        
        # Round to valid step
        sanitized = math.floor(requested_lots / vol_step) * vol_step
        sanitized = max(min_vol, min(sanitized, max_vol))
        
        # Handle precision
        step_str = str(vol_step).split('.')
        precision = len(step_str[1]) if len(step_str) > 1 else 0
        
        return round(sanitized, precision)
    
    def check_daily_limits(self) -> bool:
        """Check if daily limits have been hit."""
        account = mt5.account_info()
        if account is None:
            return True
        
        if account.profit <= self.daily_loss_limit:
            logger.info(f"Daily loss limit reached: {account.profit}")
            return False
        
        if account.profit >= self.daily_win_limit:
            logger.info(f"Daily profit target reached: {account.profit}")
            return False
        
        return True

# ----------------- TRADE EXECUTOR -----------------
class TradeExecutor:
    """Handles order execution with proper validation."""
    
    def __init__(self, magic: int):
        self.magic = magic
    
    def get_filling_mode(self, symbol: str) -> int:
        """Get appropriate filling mode."""
        fill = mt5.symbol_info(symbol).filling_mode
        if fill & 1:
            return mt5.ORDER_FILLING_FOK
        if fill & 2:
            return mt5.ORDER_FILLING_IOC
        return mt5.ORDER_FILLING_RETURN
    
    def place_trade(self, symbol: str, order_type: int, lot: float, 
                   entry: float, stop_loss: float, take_profit: float,
                   comment: str = "TTrades") -> bool:
        """Place a trade with all validations."""
        
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logger.error(f"Symbol {symbol} not found")
            return False
        
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"Cannot get tick for {symbol}")
            return False
        
        # Get current price
        price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
        
        # Get digits for rounding
        digits = symbol_info.digits
        
        # Calculate final SL and TP (ensure minimum distance)
        stop_level = symbol_info.trade_stops_level * symbol_info.point
        min_distance = max(stop_level, 2 * symbol_info.point)
        
        if order_type == mt5.ORDER_TYPE_BUY:
            final_sl = min(stop_loss, price - min_distance)
            final_tp = max(take_profit, price + min_distance)
        else:
            final_sl = max(stop_loss, price + min_distance)
            final_tp = min(take_profit, price - min_distance)
        
        # Round everything
        final_sl = round(final_sl, digits)
        final_tp = round(final_tp, digits)
        price = round(price, digits)
        
        # Build request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": order_type,
            "price": price,
            "sl": final_sl,
            "tp": final_tp,
            "magic": self.magic,
            "comment": comment,
            "type_filling": self.get_filling_mode(symbol),
            "deviation": 10,
        }
        
        # Send order
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Trade failed: {result.retcode} - {result.comment}")
            logger.error(f"Request: {request}")
            return False
        
        logger.info(f"Trade executed: {symbol} {order_type} {lot} @ {price}")
        return True
    
    def close_position(self, position) -> bool:
        """Close a specific position."""
        tick = mt5.symbol_info_tick(position.symbol)
        if tick is None:
            return False
        
        order_type = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = tick.bid if order_type == mt5.ORDER_TYPE_SELL else tick.ask
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": order_type,
            "position": position.ticket,
            "price": price,
            "magic": self.magic,
            "type_filling": self.get_filling_mode(position.symbol),
        }
        
        result = mt5.order_send(request)
        return result.retcode == mt5.TRADE_RETCODE_DONE
    
    def close_partial(self, position, percentage: float) -> bool:
        """Close a percentage of a position."""
        if percentage <= 0 or percentage >= 1:
            return False
        
        volume = round(position.volume * percentage, 3)
        if volume < MIN_LOT:
            return False
        
        tick = mt5.symbol_info_tick(position.symbol)
        if tick is None:
            return False
        
        order_type = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = tick.bid if order_type == mt5.ORDER_TYPE_SELL else tick.ask
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": volume,
            "type": order_type,
            "position": position.ticket,
            "price": price,
            "magic": self.magic,
            "type_filling": self.get_filling_mode(position.symbol),
        }
        
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"Closed {percentage*100}% of position {position.ticket}")
            return True
        return False

# ----------------- STRATEGY ENGINE (TTrades Style) -----------------
class TTradesStrategy:
    """
    Implements TTrades-style trading:
    1. Identify Market Structure (Swing Highs/Lows)
    2. Identify Order Flow (FVG, Order Blocks)
    3. Wait for Price to Retrace to Premium/Discount
    4. Enter with Stop Loss at Structure Level
    5. Manage Trade with Scaling and Trailing
    """
    
    def __init__(self, symbol: str, magic: int):
        self.symbol = symbol
        self.magic = magic
        self.risk_manager = RiskManager(RISK_PER_TRADE)
        self.executor = TradeExecutor(magic)
        
        self.max_positions = MAX_POSITIONS_PER_SYMBOL
        self.scaling_active = False
        self.scaling_count = 0
        
    def analyze(self) -> Dict[str, Any]:
        """Perform multi-timeframe analysis."""
        analysis = {
            "direction": "NEUTRAL",
            "entry": None,
            "stop_loss": None,
            "take_profit": None,
            "confidence": 0
        }
        
        # 1. Higher Timeframe Analysis (H1)
        ms_h1 = MarketStructure(self.symbol, TIMEFRAME_1H, 50)
        h1_bos = ms_h1.get_break_of_structure()
        
        # 2. Mid Timeframe Analysis (M15)
        ms_m15 = MarketStructure(self.symbol, TIMEFRAME_15M, 30)
        m15_bos = ms_m15.get_break_of_structure()
        
        # 3. FVG Detection
        fvg_m15 = FairValueGap(self.symbol, TIMEFRAME_15M).get_fvg()
        fvg_m5 = FairValueGap(self.symbol, TIMEFRAME_5M).get_fvg()
        
        # 4. Current Price
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            return analysis
        current_price = (tick.bid + tick.ask) / 2
        
        # 5. Determine Direction based on BOS
        if h1_bos["bos"] == "BULLISH" and m15_bos["bos"] != "BEARISH":
            analysis["direction"] = "BUY"
        elif h1_bos["bos"] == "BEARISH" and m15_bos["bos"] != "BULLISH":
            analysis["direction"] = "SELL"
        else:
            # Wait for alignment
            return analysis
        
        # 6. Find FVG in direction of trade
        target_fvgs = fvg_m15 if fvg_m15 else fvg_m5
        
        if analysis["direction"] == "BUY":
            # Look for bullish FVG (support)
            bullish_fvgs = [f for f in target_fvgs if f["type"] == "BULLISH"]
            if bullish_fvgs:
                # Find closest FVG below price
                closest_fvg = min(bullish_fvgs, key=lambda x: current_price - x["top"])
                if current_price > closest_fvg["top"]:
                    # Price is in FVG, look for entry
                    entry_price = closest_fvg["mid"]
                    stop_loss = closest_fvg["bottom"] - (closest_fvg["top"] - closest_fvg["bottom"]) * 0.5
                    take_profit = current_price + (current_price - stop_loss) * TARGET_R_RATIO
                    
                    analysis["entry"] = entry_price
                    analysis["stop_loss"] = stop_loss
                    analysis["take_profit"] = take_profit
                    analysis["confidence"] = 70 if h1_bos["bos"] == "BULLISH" else 50
                    
        elif analysis["direction"] == "SELL":
            # Look for bearish FVG (resistance)
            bearish_fvgs = [f for f in target_fvgs if f["type"] == "BEARISH"]
            if bearish_fvgs:
                # Find closest FVG above price
                closest_fvg = min(bearish_fvgs, key=lambda x: x["bottom"] - current_price)
                if current_price < closest_fvg["bottom"]:
                    entry_price = closest_fvg["mid"]
                    stop_loss = closest_fvg["top"] + (closest_fvg["top"] - closest_fvg["bottom"]) * 0.5
                    take_profit = current_price - (stop_loss - current_price) * TARGET_R_RATIO
                    
                    analysis["entry"] = entry_price
                    analysis["stop_loss"] = stop_loss
                    analysis["take_profit"] = take_profit
                    analysis["confidence"] = 70 if h1_bos["bos"] == "BEARISH" else 50
        
        return analysis
    
    def manage_positions(self) -> None:
        """Active position management with scaling and trailing."""
        positions = mt5.positions_get(symbol=self.symbol, magic=self.magic)
        if not positions:
            return
        
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            return
        
        current_price = (tick.bid + tick.ask) / 2
        
        for pos in positions:
            # Calculate current R
            entry = pos.price_open
            if pos.type == mt5.ORDER_TYPE_BUY:
                current_r = (current_price - entry) / (pos.sl - entry) if pos.sl else 0
                profit_target = abs(pos.tp - entry)
                current_gain = current_price - entry
            else:
                current_r = (entry - current_price) / (entry - pos.sl) if pos.sl else 0
                profit_target = abs(entry - pos.tp)
                current_gain = entry - current_price
            
            # 1. Trail Stop Loss when we've achieved 50% of target
            if current_gain >= profit_target * TRAILING_START_PERCENT:
                if pos.type == mt5.ORDER_TYPE_BUY:
                    new_sl = entry + (current_gain * TRAILING_STEP)
                else:
                    new_sl = entry - (current_gain * TRAILING_STEP)
                
                # Only update if beneficial
                if (pos.type == mt5.ORDER_TYPE_BUY and new_sl > pos.sl) or \
                   (pos.type == mt5.ORDER_TYPE_SELL and new_sl < pos.sl):
                    self.executor.modify_sl(pos.ticket, new_sl)
            
            # 2. Partial Profit Taking at 1R and 2R
            if current_r >= 1.0 and pos.volume > MIN_LOT * 2:
                self.executor.close_partial(pos, 0.25)
            
            if current_r >= 2.0:
                self.executor.close_partial(pos, 0.25)
            
            # 3. Full Close at 3R
            if current_r >= TARGET_R_RATIO:
                self.executor.close_position(pos)
    
    def check_entry(self) -> bool:
        """Check if we should enter a trade."""
        # 1. Check daily limits
        if not self.risk_manager.check_daily_limits():
            return False
        
        # 2. Check existing positions
        positions = mt5.positions_get(symbol=self.symbol, magic=self.magic)
        if positions and len(positions) >= self.max_positions:
            return False
        
        # 3. Check cooldown
        # (Implement cooldown if needed)
        
        # 4. Get analysis
        analysis = self.analyze()
        
        if analysis["direction"] == "NEUTRAL":
            return False
        
        if analysis["confidence"] < 50:
            return False
        
        # 5. Calculate position size
        entry = analysis["entry"]
        stop_loss = analysis["stop_loss"]
        take_profit = analysis["take_profit"]
        
        lot = self.risk_manager.calculate_position_size(self.symbol, entry, stop_loss)
        
        # 6. Place trade
        order_type = mt5.ORDER_TYPE_BUY if analysis["direction"] == "BUY" else mt5.ORDER_TYPE_SELL
        
        return self.executor.place_trade(
            self.symbol, order_type, lot, entry, stop_loss, take_profit
        )
    
    def execute(self) -> None:
        """Main execution loop for this symbol."""
        # Manage existing positions first
        self.manage_positions()
        
        # Check for new entry
        self.check_entry()

# ----------------- SCALING STRATEGY (For Smaller Accounts) -----------------
class ScalpingStrategy(TTradesStrategy):
    """
    Modified strategy for smaller accounts (< $100).
    Uses lower timeframes and tighter stops.
    """
    
    def __init__(self, symbol: str, magic: int):
        super().__init__(symbol, magic)
        self.risk_manager = RiskManager(SCALING_RISK_PER_TRADE)
        self.max_positions = SCALING_MAX_TRADES
        
    def analyze(self) -> Dict[str, Any]:
        """Scalping analysis using M5 and M1."""
        analysis = {
            "direction": "NEUTRAL",
            "entry": None,
            "stop_loss": None,
            "take_profit": None,
            "confidence": 0
        }
        
        # 1. M5 Market Structure
        ms_m5 = MarketStructure(self.symbol, TIMEFRAME_5M, 30)
        m5_bos = ms_m5.get_break_of_structure()
        
        # 2. M1 FVG
        fvg_m1 = FairValueGap(self.symbol, TIMEFRAME_1M).get_fvg()
        
        # 3. Current Price
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            return analysis
        current_price = (tick.bid + tick.ask) / 2
        
        # 4. Direction
        if m5_bos["bos"] == "BULLISH":
            analysis["direction"] = "BUY"
        elif m5_bos["bos"] == "BEARISH":
            analysis["direction"] = "SELL"
        else:
            return analysis
        
        # 5. Look for FVG entry
        if analysis["direction"] == "BUY":
            bullish_fvgs = [f for f in fvg_m1 if f["type"] == "BULLISH"]
            if bullish_fvgs:
                closest_fvg = min(bullish_fvgs, key=lambda x: current_price - x["top"])
                if current_price > closest_fvg["top"]:
                    analysis["entry"] = closest_fvg["mid"]
                    analysis["stop_loss"] = closest_fvg["bottom"] - (closest_fvg["top"] - closest_fvg["bottom"]) * 0.3
                    analysis["take_profit"] = current_price + (current_price - analysis["stop_loss"]) * SCALING_TARGET_R
                    analysis["confidence"] = 60
        
        elif analysis["direction"] == "SELL":
            bearish_fvgs = [f for f in fvg_m1 if f["type"] == "BEARISH"]
            if bearish_fvgs:
                closest_fvg = min(bearish_fvgs, key=lambda x: x["bottom"] - current_price)
                if current_price < closest_fvg["bottom"]:
                    analysis["entry"] = closest_fvg["mid"]
                    analysis["stop_loss"] = closest_fvg["top"] + (closest_fvg["top"] - closest_fvg["bottom"]) * 0.3
                    analysis["take_profit"] = current_price - (analysis["stop_loss"] - current_price) * SCALING_TARGET_R
                    analysis["confidence"] = 60
        
        return analysis

# ----------------- PASSKEY CHECK -----------------
PASSKEY_FILE = "bot_access.json"
CORRECT_PASSKEY = "1234567890#12345678901#"
system_id = platform.node() + "_" + platform.system() + "_" + platform.release()
access_granted = False

if os.path.exists(PASSKEY_FILE):
    try:
        with open(PASSKEY_FILE, "r") as f:
            if json.load(f).get(system_id) == CORRECT_PASSKEY:
                access_granted = True
    except:
        pass

if not access_granted:
    if input("Enter bot passkey: ") == CORRECT_PASSKEY:
        with open(PASSKEY_FILE, "w") as f:
            json.dump({system_id: CORRECT_PASSKEY}, f)
    else:
        exit()

# ----------------- MAIN LOOP -----------------
def initialize_mt5():
    if not mt5.initialize():
        logger.error(f"MT5 initialize failed: {mt5.last_error()}")
        return False
    logger.info("MT5 initialized successfully")
    return True

def main():
    if not initialize_mt5():
        return
    
    # Setup strategies based on account balance
    account = mt5.account_info()
    if account is None:
        logger.error("Cannot get account info")
        return
    
    strategies = {}
    for i, symbol in enumerate(SYMBOLS):
        magic = MAGIC_BASE + i
        
        # Choose strategy based on account size
        if account.balance < 100:
            strategies[symbol] = ScalpingStrategy(symbol, magic)
        else:
            strategies[symbol] = TTradesStrategy(symbol, magic)
    
    logger.info(f"Trading started with {len(strategies)} strategies")
    
    try:
        while True:
            # Update account info
            account = mt5.account_info()
            if account is None:
                time.sleep(1)
                continue
            
            # Check daily limits
            if account.profit <= DAILY_LOSS_LIMIT:
                logger.warning(f"Daily loss limit reached: {account.profit:.2f}")
                time.sleep(300)  # Wait 5 minutes
                continue
                
            if account.profit >= DAILY_PROFIT_TARGET:
                logger.info(f"Daily profit target reached: {account.profit:.2f}")
                time.sleep(300)
                continue
            
            # Execute each strategy
            for symbol, strategy in strategies.items():
                try:
                    strategy.execute()
                except Exception as e:
                    logger.error(f"Error in strategy for {symbol}: {e}")
            
            # Display dashboard
            os.system('cls' if os.name == 'nt' else 'clear')
            print("=" * 80)
            print(f" TTrades Bot | {datetime.now().strftime('%H:%M:%S')} | Balance: {account.balance:.2f} | Profit: {account.profit:.2f}")
            print("=" * 80)
            print(f"{'Symbol':<20} | {'Strategy':<10} | {'Positions':<10} | {'Status'}")
            print("-" * 80)
            
            for symbol, strategy in strategies.items():
                positions = mt5.positions_get(symbol=symbol, magic=strategy.magic)
                pos_count = len(positions) if positions else 0
                strategy_type = "Scalping" if isinstance(strategy, ScalpingStrategy) else "Standard"
                status = "Active" if pos_count > 0 else "Waiting"
                print(f"{symbol:<20} | {strategy_type:<10} | {pos_count:<10} | {status}")
            
            print("=" * 80)
            
            # Sleep before next iteration
            time.sleep(SLEEP_INTERVAL)
            
    except KeyboardInterrupt:
        logger.info("Manual stop detected")
    except Exception as e:
        logger.error(f"Main loop error: {e}")
    finally:
        mt5.shutdown()
        logger.info("MT5 connection closed")

if __name__ == "__main__":
    main()