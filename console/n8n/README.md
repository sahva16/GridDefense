# GridDefense phone alerts (n8n + ntfy)

When GridDefense raises an alarm, the console sends it to **n8n**, and n8n pushes it to your
phone through the free **ntfy** app. No account is needed for ntfy.

```
GridDefense console  ──(alarm, JSON)──▶  n8n workflow  ──▶  ntfy.sh  ──▶  your phone
```

Example of what arrives on the phone (scenario S3):

```
GridDefense ALARM: Coordinated attack, bus 9, 14
GridDefense ALARM (HIGH)
Coordinated attack on bus 9, 14
Fusion score 0.64 (alarm at 0.40)
Physics checks failed: bus 9: real-power balance, reactive-power balance, voltage vs neighbours; bus 14: reactive-power balance, voltage vs neighbours
Also flagged nearby: bus 7, 10, 13
Time ...
Models: bundle 58a97441d9b5 (Notebook models · verified)
```

## 1. Phone: install ntfy and pick a topic (2 minutes)

1. Install **ntfy** (Android: Google Play or F-Droid · iPhone: App Store).
2. Tap **+**, choose a topic name and subscribe. Make it hard to guess, for example
   `griddefense-sahva-7k3q`. Anyone who knows the name can read it, so only demo alarms go there.
3. Quick check from your laptop (Windows PowerShell or Command Prompt):
   `curl -d "hello from GridDefense" ntfy.sh/griddefense-sahva-7k3q`
   Your phone should buzz. If it does, the phone part works.

Tip: alarms are sent with **urgent** priority. In the ntfy app you can let urgent messages ring
even in Do Not Disturb (topic settings), which is nice for the open day.

## 2. n8n: import the workflow (5 minutes)

Use **either** option:

- **n8n Cloud** (no install): sign up at n8n.io, which gives you a free trial.
- **On your laptop**: install Node.js (LTS) from nodejs.org, then:
  1. Open a **new** Command Prompt (a window opened before the install won't find Node) and
     check with `node -v`.
  2. Run `npx n8n`. Type `y` when it asks to install. The first time takes a few minutes.
  3. Wait for *"Editor is now accessible via: http://localhost:5678"*, then open that address.
  4. Create the owner account (it stays on your laptop).
  5. Keep the Command Prompt window open; closing it stops n8n. Next time, `npx n8n` starts in
     seconds.

Then:

1. **Workflows → Import from file** → choose `griddefense_phone_alert.json` (this folder).
2. Open the node **"Push to phone (ntfy, no account)"**. In the URL, replace
   `griddefense-CHANGE-THIS-TO-YOUR-OWN-NAME` with your topic from step 1.
3. **Save**, then switch the workflow to **Active** (toggle at the top right).
4. Open the node **"GridDefense alarm (webhook)"** and copy the **Production URL**. It ends in
   `/webhook/griddefense-alarm`.
   - Use the *Production* URL, not the *Test* URL. The test URL only works while n8n is
     "listening for a test event".

The Telegram node is switched off. Turn it on only if you also want Telegram messages.

## 3. Console: connect it (1 minute)

1. Start GridDefense as usual and open http://localhost:8000.
2. Click **⚙ Settings** (top right).
3. Paste the Production URL into **n8n webhook URL** and press **Save**.
4. Press **Test**. The console shows "Test alert delivered." and your phone gets
   *"GridDefense test alert"*.
5. Run scenario **S3**. Your phone gets the alarm above. In the Alarms list the alarm shows
   **phone ✓**.

**Phone alerts** in Settings controls what is sent:
- **Simulated attacks only** (default): scenarios and the attack simulator.
- **Every alarm**: also alarms from the live replay of the test set.
- **Off**.

You can also set the URL before starting: `set N8N_WEBHOOK_URL=https://...` (Windows) or
`export N8N_WEBHOOK_URL=https://...` (Mac/Linux).

## What has been tested

- **Console → webhook: tested automatically.** The test
  `test_alarm_is_sent_to_n8n_webhook_and_normal_is_not` checks that:
  - the Test button delivers a test message;
  - normal operation (S0) sends nothing;
  - the S3 attack sends one alarm with type Coordinated, buses 9 and 14, a fusion score at or
    above the threshold, and the verified models.
- Checked by hand: S1 sends an Additive alarm on bus 4; the 0.5 % attack in S7 stays
  undetected, so nothing is sent.
- **n8n → ntfy → phone: not tested yet.** Do it once on your own network with steps 1–3 above.

## If something doesn't work

| Symptom | Fix |
|---|---|
| Test says "Failed: 404" | The workflow is not **Active**, or you pasted the Test URL instead of the Production URL. |
| Test says "Failed: ... connect ..." | n8n is not running, or the URL is wrong. Open the URL's address in a browser to check. |
| Test delivered, but phone silent | The topic name in the HTTP node and in the ntfy app differ (check spelling). |
| Alarms appear in the console but no phone ✓ | Settings → Phone alerts is **Off**, or the alarm came from live replay while it is set to "Simulated attacks only". |
