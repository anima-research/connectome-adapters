import socketio
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
sio = socketio.AsyncClient()

@sio.event
async def connect():
    logging.info("Connected to Telegram adapter")

@sio.event
async def disconnect():
    logging.info("Disconnected from Telegram adapter")

@sio.event
async def telegram_message(data):
    logging.info(f"Received message: {data}")

    # Simple example: echo the message back
    if 'text' in data and data['text']:
        response = {
            "conversation_id": data['chat_id'],
            "text": f"Echo: {data['text']}",
            "reply_to_message_id": data['message_id']
        }
        await sio.emit('response_ready', response)

async def main():
    server_url = "http://localhost:8080"
    logging.info(f"Connecting to Telegram adapter at {server_url}")

    try:
        await sio.connect(server_url)
        await sio.wait()
    except Exception as e:
        logging.error(f"Error: {e}")
    finally:
        if sio.connected:
            await sio.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
