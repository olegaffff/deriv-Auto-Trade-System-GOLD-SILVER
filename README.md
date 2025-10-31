# Deriv Gold & Silver Multiplier Scalper

A Python-based trading bot for the Deriv platform that implements an automated scalping strategy for Gold (XAU/USD) and Silver (XAG/USD) using multiplier contracts.

## Features

- Real-time market data monitoring for Gold and Silver
- Technical analysis using RSI, Bollinger Bands, and Stochastic indicators
- Automated trading with configurable parameters
- Auto-reconnection to handle connection issues
- Risk management with take-profit and stop-loss settings
- Trading statistics and activity logging
- Clean GUI interface built with tkinter

## Requirements

- Python 3.7+
- Packages:
  - tkinter
  - websockets
  - numpy

## Installation

pip install websockets numpy
photo : https://i.ibb.co/5g5gJ0fc/32.png

2. Enter your Deriv API token in the connection field.

3. Click "Connect" to establish a connection with Deriv's API.

4. Configure your trading parameters:
- Stake amount
- Multiplier
- Take profit percentage
- Stop loss percentage
- Maximum open trades
- Cooldown period between trades

5. Click "Start Auto" to begin automated trading.

## Trading Strategy

The bot analyzes market conditions using:
- RSI (Relative Strength Index)
- Bollinger Bands
- Stochastic Oscillator

It identifies potential buy/sell signals when:
- RSI < 35, Stochastic < 25, and price is below the lower Bollinger Band (BUY signal)
- RSI > 65, Stochastic > 75, and price is above the upper Bollinger Band (SELL signal)

## Risk Warning

Trading financial instruments carries a high level of risk and may not be suitable for all investors. The bot is provided as-is, and you are responsible for any losses incurred while using it. Always test with a demo account before using real funds.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This software is for educational purposes only. The developers are not responsible for any financial losses incurred while using this software.
