# Slack Notifications Setup Guide

## Overview
Get real-time trading alerts sent directly to your Slack workspace!

## Setup Steps

### 1. Create a Slack Incoming Webhook

1. Go to https://api.slack.com/apps
2. Click "Create New App"
3. Choose "From scratch"
4. Enter app name: "Ozzy Trading Bot"
5. Select your workspace
6. Click "Create App"

### 2. Enable Incoming Webhooks

1. In your app settings, click "Incoming Webhooks"
2. Toggle "Activate Incoming Webhooks" to ON
3. Click "Add New Webhook to Workspace"
4. Select the channel where you want notifications
5. Click "Allow"

### 3. Copy Your Webhook URL

You'll see a webhook URL like:
```
https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX
```

Copy this URL!

### 4. Add to Your .env File

Edit `/home/rick/ozzy-simple/.env` and add:

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### 5. Test the Integration

Run the test script:

```bash
cd /home/rick/ozzy-simple
source venv/bin/activate
python notifications/slack_notifier.py "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

You should see:
```
✅ Slack notification sent successfully!
```

And receive a test message in Slack!

### 6. Restart the Bot

Stop the current bot (Ctrl+C) and restart:

```bash
python scripts/test_live_stream.py --symbol BTCUSDT --duration 43200 --decision-interval 60
```

You should see:
```
📱 Slack notifications enabled
```

## Notification Types

### 🟢 Position Opened
- Symbol and entry price
- Position size
- AI confidence level
- Reasoning

### 🔴 Position Closed
- Exit price and P&L
- Win/Loss outcome
- Closing reason (AI, TP, SL)

### 📊 Daily Summary
- Total P&L
- Win rate
- Number of trades
- Open positions

### 🚀 Test Start/Complete
- Duration
- Performance summary
- Final results

## Troubleshooting

### No notifications received?

1. Check `.env` file has correct webhook URL
2. Ensure webhook starts with `https://hooks.slack.com/`
3. Verify the bot restarted after adding the URL
4. Check Slack app has permission to post to your channel

### "Slack notifications disabled" message?

- The `SLACK_WEBHOOK_URL` is not set in `.env`
- This is optional - bot will work without it

### Want to disable notifications?

Remove or comment out the `SLACK_WEBHOOK_URL` line in `.env`:

```bash
# SLACK_WEBHOOK_URL=https://hooks.slack.com/...
```

## Custom Channels

Want different notifications in different channels?

1. Create multiple webhooks (one per channel)
2. Modify `slack_notifier.py` to support multiple URLs
3. Route different notification types to different channels

## Example Notification Flow

```
07:00 🚀 Trading Bot Started
      Symbol: BTCUSDT
      Duration: 12.0 hours

07:01 🟢 Position Opened: BTCUSDT
      Entry: $112,570.50
      Size: $250.00
      Confidence: 75%

07:15 🟢 Position Closed: BTCUSDT
      Exit: $113,000.00
      P&L: +$0.95 (+0.38%)
      Outcome: WIN

19:00 ✅ Trading Test Complete
      Duration: 12.0 hours
      Total P&L: +$45.67
      Win Rate: 68.4%
      Trades: 13W / 6L
```

## Next Steps

Once notifications are working:
- Run the overnight test
- Wake up to results in Slack!
- Analyze performance
- Iterate on strategy

## Support

Having issues? Check:
- Slack API status: https://status.slack.com/
- Webhook URL is correct
- Bot has permission to write to channel
- Network connection is working
