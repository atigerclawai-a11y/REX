# REX Queue Processor — One-Time Setup

Open **Terminal** and run this single command:

```bash
bash ~/Desktop/REX/install_queue_processor.sh
```

That's it. It will:
1. Install the background agent (runs every 15 min, survives reboots)
2. Test your nemobot connection at localhost:5000
3. Test Telegram delivery to your phone
4. Process the 3 prompts already waiting in the queue

**After install completes, you'll get a Telegram message when the responses are ready.**

---

## If nemobot returns an error

The processor tries `POST http://localhost:5000/api/ask` by default.
If your nemobot uses a different endpoint, edit:

```
~/Desktop/REX/rex_queue_config.json
```

Change the `"url"` and `"prompt_key"` / `"response_key"` fields to match your setup.
Then re-run: `python3 ~/Desktop/REX/rex_queue_processor.py --test`

---

## To enable email notifications (optional)

1. Go to: https://myaccount.google.com/apppasswords
2. Create a new App Password for "REX"
3. Open `~/Desktop/REX/rex_queue_config.json`
4. Set `"app_password": "your-16-char-password"` and `"enabled": true`

---

## Status check anytime

```bash
python3 ~/Desktop/REX/rex_queue_processor.py --status
```
