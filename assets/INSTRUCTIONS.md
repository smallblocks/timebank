# TimeBank — Instructions

## First Run

1. Open the **Web UI** from your StartOS Services page.
2. Tap **Parents** and log in with the default PIN: **1031**.
3. Go to **Settings** and change the PIN immediately.
4. Add your kids from the Parents dashboard.
5. Add tasks with minute values (e.g., "Make bed — 5 min", "Read 20 pages — 15 min").

Kids can now open the Web UI, tap their name, and start completing tasks.

## iPad / Tablet Install (PWA)

TimeBank is a Progressive Web App — install it to the home screen for a full-screen, app-like experience.

1. Open the TimeBank service URL in **Safari** on the iPad.
   - Use the **https** LAN address (`.local`) or a clearnet domain via Start-Tunnel — not plain `http` — so the service worker and offline caching work correctly.
2. Tap the **Share** button (box with arrow) → **Add to Home Screen**.
3. Name it "TimeBank" and tap **Add**.

The app will now launch full-screen from the home screen like a native app.

## Screen Time Pairing (iOS)

Use Apple Screen Time to lock the iPad to TimeBank so kids earn minutes before unlocking anything else.

1. **Settings → Screen Time → Downtime**: Turn on, set **All Day** (every day).
2. **App Limits → Add Limit**: Select **All Apps & Categories**, set 1 minute, enable **Block at End of Limit**.
3. **Always Allowed**: Add **Safari** to the always-allowed list.
4. **Content & Privacy → Content Restrictions → Web Content**: Select **Allowed Websites Only** and add only the TimeBank URL.
5. When kids earn enough minutes, TimeBank shows a prompt. The parent taps **Approve** in the app to confirm the screen-time grant.
6. On the iPad, the child uses **Ask For More Time** in the Screen Time prompt. The parent (on their own device) grants the minutes the bank shows are available.

This way the iPad is locked to TimeBank by default; kids work tasks to earn time, and parents approve from any device.

## Notifications

TimeBank can send push notifications (task approvals, screen-time requests) via [ntfy](https://ntfy.sh).

1. Open **Settings** in the TimeBank Web UI (logged in as parent).
2. Set the **Notification URL** to your ntfy topic — either a self-hosted ntfy instance or `https://ntfy.sh/your-private-topic`.
3. Subscribe to the same topic on your phone using the ntfy app.

## Backups

All data lives in a single SQLite file on the StartOS data volume. StartOS backups cover everything automatically — tasks, balances, history, and settings. No extra configuration needed.

## Reset Parent PIN

If you forget the parent PIN:

1. Open your StartOS dashboard.
2. Go to **TimeBank → Actions → Reset Parent PIN**.
3. The PIN resets to **1031** and all parent sessions are logged out.
4. Log in with **1031** and change it in Settings immediately.
