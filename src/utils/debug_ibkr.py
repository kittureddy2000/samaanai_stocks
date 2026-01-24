import asyncio
import os
import sys
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("debug_ibkr")

def check_env():
    logger.info("Checking environment variables...")
    host = os.environ.get('IBKR_GATEWAY_HOST')
    port = os.environ.get('IBKR_GATEWAY_PORT')
    broker_type = os.environ.get('BROKER_TYPE')
    
    logger.info(f"BROKER_TYPE: {broker_type}")
    logger.info(f"IBKR_GATEWAY_HOST: {host}")
    logger.info(f"IBKR_GATEWAY_PORT: {port}")
    
    if not host or not port:
        logger.error("❌ IBKR_GATEWAY_HOST or IBKR_GATEWAY_PORT not set!")
        return False
    return True

async def test_connection():
    if not check_env():
        return

    logger.info("Importing ib_insync...")
    try:
        from ib_insync import IB
    except ImportError:
        logger.error("❌ ib_insync not installed!")
        return

    host = os.environ.get('IBKR_GATEWAY_HOST', '127.0.0.1')
    port = int(os.environ.get('IBKR_GATEWAY_PORT', '4002'))
    client_id = int(os.environ.get('IBKR_CLIENT_ID', '999'))

    ib = IB()
    logger.info(f"Attempting to connect to {host}:{port} with clientId={client_id}...")

    try:
        await ib.connectAsync(host, port, clientId=client_id, timeout=10)
        logger.info("✅ SUCCESS: Connected to IBKR Gateway!")
        logger.info(f"Server Version: {ib.client.serverVersion()}")
        
        # Try to get account summary
        logger.info("Requesting account summary...")
        account_summary = await ib.accountSummaryAsync()
        logger.info(f"Account Summary received: {len(account_summary)} items")
        
        ib.disconnect()
        logger.info("Disconnected.")
        
    except Exception as e:
        logger.error(f"❌ Connection FAILED: {e}")
        import traceback
        logger.error(traceback.format_exc())

def main():
    logger.info("Starting IBKR connection debug script...")
    
    # Cloud Run specific: ensure event loop
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    loop.run_until_complete(test_connection())

if __name__ == "__main__":
    main()
