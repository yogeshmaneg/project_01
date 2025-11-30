# OI Tracker

This script tracks the change in Open Interest (OI) for ATM, 2 ITM, and 2 OTM options for both calls and puts. It displays the OI change in a live-updating table in the console.

## Features

-   Live OI tracking for Nifty 50, Bank Nifty, and other instruments.
-   Displays percentage change in OI at 3, 5, 10, 15, and 30-minute intervals.
-   Color-codes cells with significant OI changes.
-   Plays an alert sound when more than 50% of the cells are color-coded.

## Setup

1.  **Install dependencies:**
    ```bash
    pip install -r Dependencies/requirements.txt
    ```

2.  **Configure the application:**
    -   Create a `config.json` file from the `config.example.json` template.
    -   Fill in your `client_code` and `token_id` from your Dhan account.
    -   (Optional) Customize the `underlying` instrument and `expiry` date.

## Usage

Run the script from your terminal:

```bash
python oi_tracker.py
```

Press `Ctrl+C` to exit the application.
