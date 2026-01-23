# Interactive Brokers Migration Plan

A comprehensive guide for migrating the LLM Trading Agent from Alpaca to Interactive Brokers (IBKR).

> [!NOTE]
> This plan is for future reference. Implementation can proceed once the IBKR account is approved and you decide to migrate.

---

## Executive Summary

| Aspect | Current (Alpaca) | Proposed (IBKR) |
|--------|------------------|-----------------|
| **Broker** | Alpaca (Paper) | Interactive Brokers |
| **API** | REST API | TWS API via `ib_insync` |
| **Infrastructure** | Cloud Run (serverless) | Cloud Run + GCE VM (hybrid) |
| **Market Data** | Free (Alpaca) | yfinance (free) or IBKR subscriptions |
| **Cost** | $0/month | ~$10-15/month (VM) |

---

## Architecture

### Current Architecture (Alpaca)
```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Frontend   │────▶│  Cloud Run   │────▶│   Alpaca    │
│  React      │     │  Django API  │     │   API       │
└─────────────┘     └──────────────┘     └─────────────┘
```

### Proposed Architecture (IBKR Hybrid)
```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌─────────────┐
│  Frontend   │────▶│  Cloud Run   │────▶│   GCE VM     │────▶│   IBKR      │
│  React      │     │  Django API  │     │  IB Gateway  │     │   Servers   │
└─────────────┘     └──────────────┘     └──────────────┘     └─────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  Cloud SQL   │
                    │  PostgreSQL  │
                    └──────────────┘
```

---

## Phase 1: Create Broker Abstraction Layer

First, abstract the broker logic so both Alpaca and IBKR can be used interchangeably.

### [NEW] `src/trading/broker_base.py`

```python
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

@dataclass
class AccountInfo:
    """Standardized account information."""
    id: str
    cash: float
    buying_power: float
    portfolio_value: float
    equity: float
    last_equity: float

@dataclass
class Position:
    """Standardized position information."""
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pl: float
    unrealized_plpc: float

@dataclass
class Order:
    """Standardized order information."""
    id: str
    symbol: str
    side: str  # 'buy' or 'sell'
    qty: float
    order_type: str  # 'market', 'limit'
    status: str
    limit_price: Optional[float] = None
    filled_qty: float = 0
    filled_price: Optional[float] = None
    created_at: Optional[str] = None

class BaseBroker(ABC):
    """Abstract base class for broker implementations."""
    
    @abstractmethod
    def connect(self) -> bool:
        """Connect to the broker. Returns True if successful."""
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the broker."""
        pass
    
    @abstractmethod
    def get_account(self) -> Optional[AccountInfo]:
        """Get account information."""
        pass
    
    @abstractmethod
    def get_positions(self) -> List[Position]:
        """Get all open positions."""
        pass
    
    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol."""
        pass
    
    @abstractmethod
    def place_market_order(self, symbol: str, qty: int, side: str) -> Optional[Order]:
        """Place a market order."""
        pass
    
    @abstractmethod
    def place_limit_order(self, symbol: str, qty: int, side: str, limit_price: float) -> Optional[Order]:
        """Place a limit order."""
        pass
    
    @abstractmethod
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order status by ID."""
        pass
    
    @abstractmethod
    def get_orders_history(self, limit: int = 50) -> List[Order]:
        """Get recent order history."""
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        pass
    
    @abstractmethod
    def is_market_open(self) -> bool:
        """Check if market is open."""
        pass
```

---

### [MODIFY] `src/trading/alpaca_client.py`

Refactor to implement `BaseBroker`:

```python
from src.trading.broker_base import BaseBroker, AccountInfo, Position, Order

class AlpacaBroker(BaseBroker):
    """Alpaca implementation of BaseBroker."""
    
    def __init__(self):
        self.client = TradingClient(
            api_key=config.alpaca.api_key,
            secret_key=config.alpaca.secret_key,
            paper=True
        )
    
    def connect(self) -> bool:
        # Alpaca doesn't need explicit connection
        return True
    
    def disconnect(self) -> None:
        pass
    
    def get_account(self) -> Optional[AccountInfo]:
        account = self.client.get_account()
        return AccountInfo(
            id=str(account.id),
            cash=float(account.cash),
            buying_power=float(account.buying_power),
            portfolio_value=float(account.portfolio_value),
            equity=float(account.equity),
            last_equity=float(account.last_equity)
        )
    
    # ... rest of implementation
```

---

## Phase 2: Implement IBKR Client

### [NEW] `src/trading/ibkr_client.py`

```python
from ib_insync import IB, Stock, MarketOrder, LimitOrder, util
from src.trading.broker_base import BaseBroker, AccountInfo, Position, Order
from loguru import logger
import os

class IBKRBroker(BaseBroker):
    """Interactive Brokers implementation of BaseBroker."""
    
    def __init__(self):
        self.ib = IB()
        self.host = os.environ.get('IBKR_GATEWAY_HOST', '127.0.0.1')
        self.port = int(os.environ.get('IBKR_GATEWAY_PORT', '4001'))  # 4001=live, 4002=paper
        self.client_id = int(os.environ.get('IBKR_CLIENT_ID', '1'))
        self._connected = False
    
    def connect(self) -> bool:
        """Connect to IB Gateway."""
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id)
            self._connected = True
            logger.info(f"Connected to IBKR Gateway at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to IBKR: {e}")
            return False
    
    def disconnect(self) -> None:
        """Disconnect from IB Gateway."""
        if self._connected:
            self.ib.disconnect()
            self._connected = False
    
    def get_account(self) -> Optional[AccountInfo]:
        """Get account information from IBKR."""
        try:
            account_values = self.ib.accountSummary()
            
            # Parse account values into our standardized format
            values = {av.tag: float(av.value) for av in account_values if av.currency == 'USD'}
            
            return AccountInfo(
                id=account_values[0].account if account_values else '',
                cash=values.get('TotalCashValue', 0),
                buying_power=values.get('BuyingPower', 0),
                portfolio_value=values.get('NetLiquidation', 0),
                equity=values.get('EquityWithLoanValue', 0),
                last_equity=values.get('NetLiquidation', 0)  # IBKR doesn't have "last equity"
            )
        except Exception as e:
            logger.error(f"Error getting IBKR account: {e}")
            return None
    
    def get_positions(self) -> List[Position]:
        """Get all open positions from IBKR."""
        try:
            positions = self.ib.positions()
            return [
                Position(
                    symbol=pos.contract.symbol,
                    qty=pos.position,
                    avg_entry_price=pos.avgCost,
                    current_price=self._get_current_price(pos.contract.symbol),
                    market_value=pos.position * self._get_current_price(pos.contract.symbol),
                    unrealized_pl=0,  # Calculate separately
                    unrealized_plpc=0
                )
                for pos in positions
            ]
        except Exception as e:
            logger.error(f"Error getting IBKR positions: {e}")
            return []
    
    def place_market_order(self, symbol: str, qty: int, side: str) -> Optional[Order]:
        """Place a market order on IBKR."""
        try:
            contract = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            
            action = 'BUY' if side.lower() == 'buy' else 'SELL'
            order = MarketOrder(action, qty)
            
            trade = self.ib.placeOrder(contract, order)
            self.ib.sleep(1)  # Wait for order to be processed
            
            return Order(
                id=str(trade.order.orderId),
                symbol=symbol,
                side=side,
                qty=qty,
                order_type='market',
                status=trade.orderStatus.status,
                filled_qty=trade.orderStatus.filled,
                filled_price=trade.orderStatus.avgFillPrice
            )
        except Exception as e:
            logger.error(f"Error placing IBKR market order: {e}")
            return None
    
    def place_limit_order(self, symbol: str, qty: int, side: str, limit_price: float) -> Optional[Order]:
        """Place a limit order on IBKR."""
        try:
            contract = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            
            action = 'BUY' if side.lower() == 'buy' else 'SELL'
            order = LimitOrder(action, qty, limit_price)
            
            trade = self.ib.placeOrder(contract, order)
            self.ib.sleep(1)
            
            return Order(
                id=str(trade.order.orderId),
                symbol=symbol,
                side=side,
                qty=qty,
                order_type='limit',
                limit_price=limit_price,
                status=trade.orderStatus.status
            )
        except Exception as e:
            logger.error(f"Error placing IBKR limit order: {e}")
            return None
    
    def is_market_open(self) -> bool:
        """Check if US stock market is open."""
        try:
            # IBKR doesn't have a direct method, use trading hours check
            import datetime
            now = datetime.datetime.now(datetime.timezone.utc)
            # Simple check: M-F, 9:30 AM - 4:00 PM ET
            # For production, use IBKR's contract details for trading hours
            return now.weekday() < 5 and 14 <= now.hour < 21
        except:
            return False
    
    def _get_current_price(self, symbol: str) -> float:
        """Get current price for a symbol."""
        try:
            contract = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            ticker = self.ib.reqMktData(contract)
            self.ib.sleep(2)
            return ticker.last or ticker.close or 0
        except:
            return 0
```

---

## Phase 3: Broker Factory

### [NEW] `src/trading/broker_factory.py`

```python
import os
from src.trading.broker_base import BaseBroker

def get_broker() -> BaseBroker:
    """Factory function to get the configured broker."""
    broker_type = os.environ.get('BROKER_TYPE', 'alpaca').lower()
    
    if broker_type == 'ibkr':
        from src.trading.ibkr_client import IBKRBroker
        broker = IBKRBroker()
        broker.connect()
        return broker
    else:
        from src.trading.alpaca_client import AlpacaBroker
        return AlpacaBroker()
```

---

## Phase 4: Infrastructure Setup

### GCE VM for IB Gateway

#### Create VM
```bash
gcloud compute instances create ibkr-gateway \
    --project=samaanai-stg-1009-124126 \
    --zone=us-west1-b \
    --machine-type=e2-micro \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size=20GB \
    --tags=ibkr-gateway
```

#### Firewall Rule (Internal Only)
```bash
gcloud compute firewall-rules create allow-ibkr-internal \
    --project=samaanai-stg-1009-124126 \
    --direction=INGRESS \
    --action=ALLOW \
    --rules=tcp:4001,tcp:4002 \
    --source-ranges=10.0.0.0/8 \
    --target-tags=ibkr-gateway
```

#### Install IB Gateway on VM
```bash
# SSH into VM
gcloud compute ssh ibkr-gateway --zone=us-west1-b

# Install Java (required for IB Gateway)
sudo apt update
sudo apt install -y openjdk-11-jre-headless unzip

# Download IB Gateway (headless version)
wget https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh
chmod +x ibgateway-stable-standalone-linux-x64.sh
./ibgateway-stable-standalone-linux-x64.sh

# Install IBC for automated login
# (IBC manages gateway restarts and auto-login)
wget https://github.com/IbcAlpha/IBC/releases/download/3.18.0/IBCLinux-3.18.0.zip
unzip IBCLinux-3.18.0.zip -d ~/ibc
```

#### Configure IBC (`~/ibc/config.ini`)
```ini
IbLoginId=YOUR_IB_USERNAME
IbPassword=YOUR_IB_PASSWORD
TradingMode=paper  # or 'live'
AcceptIncomingConnectionAction=accept
```

#### Systemd Service (`/etc/systemd/system/ibgateway.service`)
```ini
[Unit]
Description=IB Gateway
After=network.target

[Service]
Type=simple
User=your_username
ExecStart=/home/your_username/ibc/gatewaystart.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable ibgateway
sudo systemctl start ibgateway
```

---

## Phase 5: Environment Variables

### GitHub Secrets (Add these)
| Secret | Value |
|--------|-------|
| `BROKER_TYPE` | `ibkr` |
| `IBKR_GATEWAY_HOST` | VM internal IP (e.g., `10.138.0.2`) |
| `IBKR_GATEWAY_PORT` | `4002` (paper) or `4001` (live) |
| `IBKR_CLIENT_ID` | `1` |

### Update `deploy-staging.yml`
```yaml
env_vars: |
  BROKER_TYPE=${{ secrets.BROKER_TYPE }}
  IBKR_GATEWAY_HOST=${{ secrets.IBKR_GATEWAY_HOST }}
  IBKR_GATEWAY_PORT=${{ secrets.IBKR_GATEWAY_PORT }}
  IBKR_CLIENT_ID=${{ secrets.IBKR_CLIENT_ID }}
```

---

## Phase 6: Requirements Update

### `requirements.txt`
```diff
# Trading API
- alpaca-py>=0.30.0
+ alpaca-py>=0.30.0  # Keep for backward compatibility
+ ib_insync>=0.9.0   # IBKR support
```

---

## Verification Checklist

- [ ] IBKR account approved
- [ ] Paper trading enabled in IBKR account
- [ ] GCE VM created and IB Gateway installed
- [ ] IB Gateway connecting successfully
- [ ] `IBKRBroker` class tested locally
- [ ] Cloud Run can reach GCE VM (VPC connector)
- [ ] Environment variables configured
- [ ] Dashboard showing IBKR data

---

## Cost Estimate

| Component | Monthly Cost |
|-----------|-------------|
| GCE VM (e2-micro) | ~$6-10 |
| Cloud Run (existing) | ~$0-5 |
| Cloud SQL (existing) | ~$10-15 |
| IBKR Market Data (optional) | $10-50 |
| **Total** | **~$26-80/month** |

---

## Rollback Plan

If IBKR doesn't work out, revert is simple:

1. Set `BROKER_TYPE=alpaca` in environment
2. Delete GCE VM
3. No code changes needed (abstraction layer)

---

## Timeline Estimate

| Phase | Duration |
|-------|----------|
| Broker abstraction layer | 2-3 hours |
| IBKR client implementation | 4-6 hours |
| GCE VM setup | 2-3 hours |
| Testing & integration | 4-6 hours |
| **Total** | **12-18 hours** |
