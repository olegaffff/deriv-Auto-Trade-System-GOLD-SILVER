# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import asyncio
import websockets
from datetime import datetime
import threading
from collections import deque
import time
import numpy as np
import queue
import gc

# --- Global Settings ---
SCAN_INTERVAL_SEC = 3  # Time between market scans
MIN_HISTORY_LEN = 120  # Minimum data points for indicators
MAX_HISTORY_LEN = 1200 # Max data points to store

# --- Symbols for Gold & Silver Multipliers ---
SYMBOLS = {
    "XAUUSD": "frxXAUUSD",
    "XAGUSD": "frxXAGUSD",
}

class DerivMultiplierScalper:
    def __init__(self, root):
        self.root = root
        self.root.title("Deriv Gold & Silver Multiplier Scalper (Auto-Reconnect Enabled) BY HTTPS://CRACKED.MIAMI")
        self.root.geometry("1100x850")
        self.root.configure(bg='#0a0e27')

        # --- Connection State ---
        self.ws = None
        self.api_token = tk.StringVar(value="") # ضع التوكن هنا إذا أردت
        self.is_connected = False
        self.req_id = 1
        self.stop_reconnect = False # Flag to stop auto-reconnect on manual disconnect
        self.was_auto_trading = False # Remembers if auto-trading was on before disconnect
        self.loop = None

        # --- Threading & Queues ---
        self.update_queue = queue.Queue()
        self.stop_event = threading.Event()
        threading.Thread(target=self.process_ui_updates, daemon=True).start()

        # --- Account Info ---
        self.balance = tk.StringVar(value="0.00")
        self.currency = tk.StringVar(value="USD")

        # --- Market Data ---
        self.price_histories = {k: deque(maxlen=MAX_HISTORY_LEN) for k in SYMBOLS.keys()}
        self.current_prices = {k: tk.StringVar(value="--.--") for k in SYMBOLS.keys()}

        # --- Trading State ---
        self.active_contracts = {}  # contract_id -> {details}
        self.auto_trading = tk.BooleanVar(value=False)
        self.last_trade_time = {k: 0 for k in SYMBOLS.keys()} # Cooldown per symbol

        # --- Trading Parameters (UI) ---
        self.stake_amount = tk.StringVar(value="10")
        self.multiplier = tk.StringVar(value="100")
        self.take_profit_percent = tk.StringVar(value="25")
        self.stop_loss_percent = tk.StringVar(value="50")
        self.max_open_trades = tk.IntVar(value=2)
        self.cooldown_sec = tk.IntVar(value=60)

        # --- Stats ---
        self.total_trades = tk.IntVar(value=0)
        self.wins = tk.IntVar(value=0)
        self.losses = tk.IntVar(value=0)
        self.net_profit = tk.DoubleVar(value=0.0)

        self.create_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.schedule_cleanup()

    # =================================================================
    #                          UI SETUP
    # =================================================================

    def create_ui(self):
        main = tk.Frame(self.root, bg='#0a0e27')
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left_panel = tk.Frame(main, bg='#0a0e27')
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        right_panel = tk.Frame(main, bg='#0a0e27')
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # --- Connection Frame ---
        conn_frame = tk.LabelFrame(left_panel, text="🔌 Connection", bg='#1a1f3a', fg='#00ff88', font=('Arial', 11, 'bold'))
        conn_frame.pack(fill=tk.X, pady=5)
        tk.Label(conn_frame, text="API Token:", bg='#1a1f3a', fg='white').grid(row=0, column=0, padx=5, pady=5, sticky='w')
        tk.Entry(conn_frame, textvariable=self.api_token, width=35, show='*').grid(row=0, column=1, padx=5, pady=5)
        self.connect_btn = tk.Button(conn_frame, text="Connect", command=self.toggle_connection, bg='#ff3366', fg='white', width=12)
        self.connect_btn.grid(row=1, column=0, columnspan=2, pady=5)
        self.status_label = tk.Label(conn_frame, text="● Disconnected", bg='#1a1f3a', fg='#ff3366', font=('Arial', 10, 'bold'))
        self.status_label.grid(row=2, column=0, columnspan=2, pady=5)

        # --- Account Frame ---
        acc_frame = tk.LabelFrame(left_panel, text="💰 Account", bg='#1a1f3a', fg='#00ff88', font=('Arial', 11, 'bold'))
        acc_frame.pack(fill=tk.X, pady=5)
        tk.Label(acc_frame, text="Balance:", bg='#1a1f3a', fg='white').grid(row=0, column=0, sticky='w', padx=5, pady=2)
        tk.Label(acc_frame, textvariable=self.balance, bg='#1a1f3a', fg='#00ff88', font=('Arial', 14, 'bold')).grid(row=0, column=1, sticky='e', padx=5, pady=2)
        tk.Label(acc_frame, textvariable=self.currency, bg='#1a1f3a', fg='#00ff88').grid(row=0, column=2, sticky='w', padx=5, pady=2)

        # --- Market Dashboard ---
        market_frame = tk.LabelFrame(left_panel, text="📊 Markets", bg='#1a1f3a', fg='white', font=('Arial', 11, 'bold'))
        market_frame.pack(fill=tk.X, pady=5)
        tk.Label(market_frame, text="Gold (XAU/USD):", bg='#1a1f3a', fg='white', font=('Arial', 10, 'bold')).grid(row=0, column=0, sticky='w', padx=5, pady=5)
        tk.Label(market_frame, textvariable=self.current_prices["XAUUSD"], bg='#1a1f3a', fg='#FFD700', font=('Arial', 12, 'bold')).grid(row=0, column=1, sticky='e', padx=5, pady=5)
        tk.Label(market_frame, text="Silver (XAG/USD):", bg='#1a1f3a', fg='white', font=('Arial', 10, 'bold')).grid(row=1, column=0, sticky='w', padx=5, pady=5)
        tk.Label(market_frame, textvariable=self.current_prices["XAGUSD"], bg='#1a1f3a', fg='#C0C0C0', font=('Arial', 12, 'bold')).grid(row=1, column=1, sticky='e', padx=5, pady=5)

        # --- Auto Trading Controls ---
        auto_frame = tk.LabelFrame(left_panel, text="🤖 Auto Trading", bg='#1a1f3a', fg='#ff3366', font=('Arial', 11, 'bold'))
        auto_frame.pack(fill=tk.X, pady=5)
        self.auto_btn = tk.Button(auto_frame, text="▶ Start Auto", command=self.toggle_auto, bg='#ff3366', fg='white', font=('Arial', 10, 'bold'), width=14)
        self.auto_btn.grid(row=0, column=0, columnspan=2, pady=10)
        self.auto_status_label = tk.Label(auto_frame, text="● OFF", bg='#1a1f3a', fg='#ff3366', font=('Arial', 10, 'bold'))
        self.auto_status_label.grid(row=1, column=0, columnspan=2)

        params = {
            "Stake ($)": self.stake_amount,
            "Multiplier (x)": self.multiplier,
            "Take Profit (%)": self.take_profit_percent,
            "Stop Loss (%)": self.stop_loss_percent,
            "Max Open Trades": self.max_open_trades,
            "Cooldown (s)": self.cooldown_sec
        }
        r = 2
        for label, var in params.items():
            tk.Label(auto_frame, text=label, bg='#1a1f3a', fg='white').grid(row=r, column=0, sticky='w', padx=5, pady=3)
            tk.Entry(auto_frame, textvariable=var, width=10, bg='#2a2f4a', fg='white').grid(row=r, column=1, sticky='e', padx=5, pady=3)
            r += 1

        # --- Statistics ---
        stats_frame = tk.LabelFrame(left_panel, text="📈 Statistics", bg='#1a1f3a', fg='white', font=('Arial', 11, 'bold'))
        stats_frame.pack(fill=tk.X, pady=5)
        tk.Label(stats_frame, text="Net Profit:", bg='#1a1f3a', fg='white').grid(row=0, column=0, sticky='w', padx=5, pady=2)
        tk.Label(stats_frame, textvariable=self.net_profit, bg='#1a1f3a', fg='#00ff88', font=('Arial', 12, 'bold')).grid(row=0, column=1, padx=5, pady=2)
        tk.Label(stats_frame, text="Trades:", bg='#1a1f3a', fg='white').grid(row=1, column=0, sticky='w', padx=5, pady=2)
        tk.Label(stats_frame, textvariable=self.total_trades, bg='#1a1f3a', fg='white').grid(row=1, column=1, padx=5, pady=2)
        tk.Label(stats_frame, text="Wins:", bg='#1a1f3a', fg='white').grid(row=2, column=0, sticky='w', padx=5, pady=2)
        tk.Label(stats_frame, textvariable=self.wins, bg='#1a1f3a', fg='#00ff88').grid(row=2, column=1, padx=5, pady=2)
        tk.Label(stats_frame, text="Losses:", bg='#1a1f3a', fg='white').grid(row=3, column=0, sticky='w', padx=5, pady=2)
        tk.Label(stats_frame, textvariable=self.losses, bg='#1a1f3a', fg='#ff3366').grid(row=3, column=1, padx=5, pady=2)

        # --- Log ---
        log_frame = tk.LabelFrame(right_panel, text="📋 Activity Log", bg='#1a1f3a', fg='white', font=('Arial', 11, 'bold'))
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = scrolledtext.ScrolledText(log_frame, bg='#0f1419', fg='#00ccff', state='disabled', font=('Consolas', 10))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    # =================================================================
    #                     CORE CONNECTION & LOGIC
    # =================================================================

    def log(self, message, level='INFO'):
        timestamp = datetime.now().strftime("%H:%M:%S")
        color_map = {'INFO': '#00ccff', 'SUCCESS': '#00ff88', 'ERROR': '#ff3366',
                     'WARNING': '#ffaa00', 'TRADE': '#FFD700', 'RESULT': '#FFFFFF'}
        
        def _log():
            self.log_text.config(state='normal')
            self.log_text.insert(tk.END, f"[{timestamp}] ", 'timestamp')
            self.log_text.insert(tk.END, f"{message}\n", level)
            self.log_text.tag_config('timestamp', foreground='#777')
            self.log_text.tag_config(level, foreground=color_map.get(level, '#FFFFFF'))
            self.log_text.see(tk.END)
            self.log_text.config(state='disabled')
        
        self.root.after(0, _log)

    def process_ui_updates(self):
        while not self.stop_event.is_set():
            try:
                task = self.update_queue.get(timeout=0.1)
                task()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"UI update error: {e}")

    def on_closing(self):
        if self.is_connected:
            self.disconnect()
        self.stop_event.set()
        self.root.destroy()

    def schedule_cleanup(self):
        gc.collect()
        self.root.after(300000, self.schedule_cleanup) # Every 5 minutes

    def toggle_connection(self):
        if self.is_connected:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        token = self.api_token.get().strip()
        if not token:
            messagebox.showerror("Error", "API Token is required.")
            return
        
        # --- NEW: Arm the auto-reconnect mechanism ---
        self.stop_reconnect = False
        self.log("Connecting to Deriv API...")
        threading.Thread(target=self.run_websocket_client, daemon=True).start()

    def disconnect(self):
        # --- NEW: Disarm auto-reconnect for manual disconnect ---
        self.stop_reconnect = True
        self.is_connected = False
        
        # Stop auto-trading if it's on
        if self.auto_trading.get():
            self.auto_trading.set(False)
            self.update_auto_trade_ui()
            self.log("Auto trading STOPPED due to disconnect.", "WARNING")

        if self.ws and self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.ws.close)

        self.log("Disconnected by user.", "WARNING")
        self.update_ui_connection_status()

    def run_websocket_client(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.websocket_handler())
        finally:
            self.loop.close()

    async def websocket_handler(self):
        uri = "wss://ws.derivws.com/websockets/v3?app_id=1089"
        
        # --- NEW: Auto-reconnect loop ---
        while not self.stop_reconnect:
            try:
                async with websockets.connect(uri) as ws:
                    self.ws = ws
                    await self.on_open() # Authorize and subscribe
                    async for message in ws:
                        await self.on_message(json.loads(message))
            except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError) as e:
                self.is_connected = False
                
                # If it's a manual disconnect, break the loop
                if self.stop_reconnect:
                    self.log("Connection closed.", "INFO")
                    break
                
                # --- Auto-reconnect logic ---
                self.log(f"Connection lost: {e}", "ERROR")
                
                # Remember if auto-trading was on and stop it
                if self.auto_trading.get():
                    self.was_auto_trading = True
                    self.auto_trading.set(False)
                    self.update_queue.put(self.update_auto_trade_ui)

                # Update UI to show reconnecting status
                self.update_queue.put(lambda: self.status_label.config(text="● Reconnecting...", fg='#ffaa00'))
                
                await asyncio.sleep(5) # Wait 5 seconds before retrying
                self.log("Attempting to reconnect...", "WARNING")

            except Exception as e:
                self.log(f"An unexpected websocket error occurred: {e}", "ERROR")
                if self.stop_reconnect:
                    break
                await asyncio.sleep(10) # Longer delay for unknown errors

    async def on_open(self):
        self.log("Connection opened. Authorizing...", "INFO")
        await self.ws.send(json.dumps({"authorize": self.api_token.get().strip(), "req_id": self.get_req_id()}))

    def get_req_id(self):
        self.req_id += 1
        return self.req_id

    def update_ui_connection_status(self):
        if self.is_connected:
            self.status_label.config(text="● Connected", fg='#00ff88')
            self.connect_btn.config(text="Disconnect", bg="#00ff88")
        else:
            self.status_label.config(text="● Disconnected", fg='#ff3366')
            self.connect_btn.config(text="Connect", bg="#ff3366")
            if self.auto_trading.get():
                self.toggle_auto()

    async def on_message(self, data):
        msg_type = data.get('msg_type')

        if msg_type not in ['tick', 'proposal_open_contract']:
             # Reduced logging for cleaner view
             pass

        if 'error' in data:
            self.log(f"API Error: {data['error']['message']}", "ERROR")
            if data['error']['code'] == 'InvalidToken':
                self.is_connected = False
                self.stop_reconnect = True # Stop retrying with a bad token
                self.update_ui_connection_status()
            return

        if msg_type == 'authorize':
            self.is_connected = True
            self.update_ui_connection_status()
            acc = data['authorize']
            self.update_queue.put(lambda: self.balance.set(f"{acc['balance']:.2f}"))
            self.update_queue.put(lambda: self.currency.set(acc['currency']))
            self.log(f"Authorization successful. Balance: {acc['balance']} {acc['currency']}", "SUCCESS")
            
            await self.subscribe_to_ticks()
            await self.subscribe_to_open_positions()

            # --- NEW: Restart auto-trading if it was on before disconnect ---
            if self.was_auto_trading:
                self.log("Resuming auto-trading...", "INFO")
                self.auto_trading.set(True) # Set state directly
                self.update_queue.put(self.update_auto_trade_ui) # Update UI
                self.was_auto_trading = False # Reset the flag

            asyncio.create_task(self.scanner_loop())

        elif msg_type == 'tick':
            tick = data['tick']
            symbol_key = next((k for k, v in SYMBOLS.items() if v == tick['symbol']), None)
            if symbol_key:
                price = tick['quote']
                self.price_histories[symbol_key].append(price)
                self.update_queue.put(lambda p=price, sk=symbol_key: self.current_prices[sk].set(f"{p:.4f}"))

        elif msg_type == 'proposal':
            proposal = data['proposal']
            proposal_id = proposal['id']
            buy_price = proposal.get('ask_price', 0)
            
            self.log(f"Proposal received. ID: {proposal_id}, Price: ${buy_price:.2f}. Buying contract...", "TRADE")
            
            buy_request = { "buy": proposal_id, "price": buy_price, "subscribe": 1, "req_id": self.get_req_id() }
            await self.ws.send(json.dumps(buy_request))

        elif msg_type == 'buy':
            buy_resp = data['buy']
            contract_id = buy_resp['contract_id']
            self.active_contracts[contract_id] = {
                'symbol': buy_resp['longcode'],
                'buy_price': buy_resp['buy_price'],
                'start_time': buy_resp['start_time'],
                'contract_id': contract_id
            }
            self.log(f"TRADE OPENED: ID {contract_id} for ${buy_resp['buy_price']:.2f}", "TRADE")

        elif msg_type == 'proposal_open_contract':
            contract = data['proposal_open_contract']
            contract_id = contract['contract_id']

            if contract_id in self.active_contracts:
                self.active_contracts[contract_id]['current_profit'] = contract.get('profit', 0)
                
                if contract.get('is_valid_to_sell') and not contract.get('is_sold'):
                    profit_pct = (contract['profit'] / contract['buy_price']) * 100
                    target_tp = float(self.take_profit_percent.get())
                    
                    if profit_pct >= target_tp:
                        self.log(f"Take Profit hit for ID {contract_id} at {profit_pct:.2f}%. Closing position.", "INFO")
                        await self.close_position(contract_id)

            if contract.get('is_sold'):
                self.process_trade_result(contract)

    async def subscribe_to_ticks(self):
        for symbol_code in SYMBOLS.values():
            await self.ws.send(json.dumps({"ticks": symbol_code, "subscribe": 1}))
        self.log("Subscribed to Gold & Silver ticks.", "INFO")

    async def subscribe_to_open_positions(self):
        await self.ws.send(json.dumps({"proposal_open_contract": 1, "subscribe": 1}))
        self.log("Subscribed to open position updates.", "INFO")

    # =================================================================
    #                     TRADING LOGIC & STRATEGY
    # =================================================================

    def analyze_market(self, key):
        prices = list(self.price_histories[key])
        if len(prices) < MIN_HISTORY_LEN:
            return None, 0

        prices_np = np.array(prices, dtype=float)
        delta = np.diff(prices_np)
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)
        
        # Using a simple moving average for RSI calculation to avoid full recalculation
        avg_gain = np.mean(gain[-14:])
        avg_loss = np.mean(loss[-14:])
        
        rs = avg_gain / avg_loss if avg_loss != 0 else np.inf
        rsi = 100 - (100 / (1 + rs))

        sma20 = np.mean(prices_np[-20:])
        std20 = np.std(prices_np[-20:])
        bb_upper = sma20 + 2 * std20
        bb_lower = sma20 - 2 * std20

        low14 = np.min(prices_np[-14:])
        high14 = np.max(prices_np[-14:])
        stoch_k = 100 * ((prices_np[-1] - low14) / (high14 - low14)) if (high14 - low14) != 0 else 50
        
        score = 0
        direction = None

        if rsi < 35 and stoch_k < 25 and prices_np[-1] < bb_lower:
            score = 10
            direction = "MULTUP"

        if rsi > 65 and stoch_k > 75 and prices_np[-1] > bb_upper:
            score = 10
            direction = "MULTDOWN"

        return direction, score

    async def scanner_loop(self):
        # A new scanner is started on each successful connect
        while self.is_connected:
            await asyncio.sleep(SCAN_INTERVAL_SEC)
            if not self.auto_trading.get():
                continue

            if len(self.active_contracts) >= self.max_open_trades.get():
                continue

            best_signal = {'key': None, 'direction': None, 'score': 0}

            for key in SYMBOLS.keys():
                if time.time() - self.last_trade_time[key] < self.cooldown_sec.get():
                    continue 

                direction, score = self.analyze_market(key)
                if direction and score > best_signal['score']:
                    best_signal = {'key': key, 'direction': direction, 'score': score}
            
            if best_signal['key']:
                self.log(f"Strong signal found for {best_signal['key']}: {best_signal['direction']} (Score: {best_signal['score']})", "INFO")
                self.last_trade_time[best_signal['key']] = time.time()
                await self.open_multiplier_position(best_signal['key'], best_signal['direction'])

    async def open_multiplier_position(self, key, direction):
        try:
            stake = float(self.stake_amount.get())
            mult = int(self.multiplier.get())
            sl_pct = float(self.stop_loss_percent.get())
            tp_pct = float(self.take_profit_percent.get())
            
            stop_loss_amount = round(stake * (sl_pct / 100), 2)
            take_profit_amount = round(stake * (tp_pct / 100), 2)

            proposal_request = {
                "proposal": 1, "amount": stake, "basis": "stake", "contract_type": direction,
                "currency": self.currency.get(), "symbol": SYMBOLS[key], "multiplier": mult,
                "limit_order": { "stop_loss": stop_loss_amount, "take_profit": take_profit_amount },
                "req_id": self.get_req_id()
            }
            
            self.log(f"Getting proposal for {key} {direction}...", "INFO")
            if self.ws:
                await self.ws.send(json.dumps(proposal_request))
        except Exception as e:
            self.log(f"Error placing trade: {e}", "ERROR")

    async def close_position(self, contract_id):
        if contract_id in self.active_contracts and self.ws:
            try:
                await self.ws.send(json.dumps({"sell": contract_id, "price": 0, "req_id": self.get_req_id()}))
            except Exception as e:
                self.log(f"Error closing position {contract_id}: {e}", "ERROR")

    def process_trade_result(self, contract):
        contract_id = contract['contract_id']
        if contract_id in self.active_contracts:
            profit = contract.get('profit', 0)
            
            self.update_queue.put(lambda: self.total_trades.set(self.total_trades.get() + 1))
            self.update_queue.put(lambda: self.net_profit.set(round(self.net_profit.get() + profit, 2)))
            
            if profit >= 0:
                self.update_queue.put(lambda: self.wins.set(self.wins.get() + 1))
                self.log(f"TRADE WON: ID {contract_id} | Profit: ${profit:.2f}", "RESULT")
            else:
                self.update_queue.put(lambda: self.losses.set(self.losses.get() + 1))
                self.log(f"TRADE LOST: ID {contract_id} | Loss: ${profit:.2f}", "RESULT")

            del self.active_contracts[contract_id]

    def toggle_auto(self):
        if not self.is_connected:
            messagebox.showwarning("Not Connected", "Please connect to the API first.")
            self.auto_trading.set(False)
            return

        current_state = self.auto_trading.get()
        new_state = not current_state

        if new_state: # If trying to turn ON
             try:
                float(self.stake_amount.get())
                int(self.multiplier.get())
                float(self.take_profit_percent.get())
                float(self.stop_loss_percent.get())
                int(self.max_open_trades.get())
                int(self.cooldown_sec.get())
                self.auto_trading.set(True)
                self.log("Auto trading STARTED.", "SUCCESS")
             except ValueError:
                messagebox.showerror("Invalid Input", "Please ensure all trading parameters are valid numbers.")
                return # Don't change the UI if validation fails
        else: # If turning OFF
            self.auto_trading.set(False)
            self.log("Auto trading STOPPED.", "WARNING")
        
        self.update_auto_trade_ui()

    def update_auto_trade_ui(self):
        if self.auto_trading.get():
            self.auto_btn.config(text="⏹ Stop Auto", bg='#00ff88')
            self.auto_status_label.config(text="● ON", fg='#00ff88')
        else:
            self.auto_btn.config(text="▶ Start Auto", bg='#ff3366')
            self.auto_status_label.config(text="● OFF", fg='#ff3366')


if __name__ == "__main__":
    root = tk.Tk()
    app = DerivMultiplierScalper(root)
    root.mainloop()
