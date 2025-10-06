import requests
import os
from collections import defaultdict
import datetime

# --- Configuration ---
# Get your credentials from the Amadeus for Developers portal:
# https://developers.amadeus.com/
AMADEUS_CLIENT_ID = os.environ.get("AMADEUS_CLIENT_ID", "YOUR_AMADEUS_CLIENT_ID")
AMADEUS_CLIENT_SECRET = os.environ.get("AMADEUS_CLIENT_SECRET", "YOUR_AMADEUS_CLIENT_SECRET")

# Amadeus API endpoint URLs (using the test environment)
TOKEN_URL = "https://test.api.amadeus.com/v1/security/oauth2/token"
# This endpoint is designed to find the cheapest dates for a trip.
FLIGHT_DATES_URL = "https://test.api.amadeus.com/v1/shopping/flight-dates"

def get_amadeus_token():
    """
    Retrieves an OAuth2 token from the Amadeus API.

    Returns:
        str: The access token, or None if an error occurs.
    """
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    body = {
        "grant_type": "client_credentials",
        "client_id": AMADEUS_CLIENT_ID,
        "client_secret": AMADEUS_CLIENT_SECRET
    }
    try:
        response = requests.post(TOKEN_URL, headers=headers, data=body)
        response.raise_for_status()
        print("✅ Access token retrieved successfully.")
        return response.json().get("access_token")
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to get Amadeus token: {e}")
        if e.response:
            print(f"   Error details: {e.response.json()}")
        return None

def find_cheapest_dates(token, origin, destination):
    """
    Searches for the cheapest flight dates over the next year for a given route.

    Args:
        token (str): The Amadeus API access token.
        origin (str): The origin airport/city code (e.g., "MAD").
        destination (str): The destination airport/city code (e.g., "BOS").

    Returns:
        list: A list of flight date offers, or an empty list if an error occurs.
    """
    print(f"\n✈️  Finding cheapest dates for: {origin} -> {destination}...")
    headers = {
        "Authorization": f"Bearer {token}"
    }
    params = {
        "origin": origin,
        "destination": destination,
        "oneWay": "true" # Simpler for finding cheapest outbound dates
    }

    try:
        response = requests.get(FLIGHT_DATES_URL, headers=headers, params=params)
        response.raise_for_status()
        print("✅ Cheapest dates received!")
        data = response.json()
        return data.get("data", [])
    except requests.exceptions.RequestException as e:
        print(f"❌ An error occurred while searching for cheapest dates: {e}")
        if e.response:
            print(f"   Error details: {e.response.json()}")
        return []

def display_cheapest_month(results, origin, destination):
    """
    Analyzes flight date results to find and display the cheapest option per month.

    Args:
        results (list): A list of flight date offers.
        origin (str): The origin airport/city code.
        destination (str): The destination airport/city code.
    """
    if not results:
        print("\n😕 No flight results found. The test API might not have data for this route.")
        return

    cheapest_by_month = {}
    overall_cheapest_offer = None

    for offer in results:
        try:
            date_str = offer.get("departureDate")
            price = float(offer.get("price", {}).get("total"))
            month_key = datetime.datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m")

            # Check for overall cheapest
            if overall_cheapest_offer is None or price < float(overall_cheapest_offer.get("price").get("total")):
                overall_cheapest_offer = offer

            # Check for cheapest in that month
            if month_key not in cheapest_by_month or price < float(cheapest_by_month[month_key].get("price").get("total")):
                cheapest_by_month[month_key] = offer
        except (ValueError, TypeError, KeyError):
            # Skip offers with malformed data
            continue

    print(f"\n--- Cheapest Flight per Month ({origin} -> {destination}) ---")
    sorted_months = sorted(cheapest_by_month.keys())
    for month in sorted_months:
        offer = cheapest_by_month[month]
        price = offer.get("price", {}).get("total")
        date = offer.get("departureDate")
        month_name = datetime.datetime.strptime(date, "%Y-%m-%d").strftime("%B %Y")
        print(f"  - {month_name+':':<15} ${price} on {date}")

    if overall_cheapest_offer:
        print("\n--- 🏆 Overall Cheapest Trip Found ---")
        price = overall_cheapest_offer.get("price", {}).get("total")
        date = overall_cheapest_offer.get("departureDate")
        print(f"  💰 Price: ${price}")
        print(f"  📅 Date:  {date}")
    
    print("\n-----------------------------------------")
    print("(Note: This is test data and cannot be booked.)")

def main():
    """Main function to run the flight checker application."""
    print("=====================================================")
    print("   Amadeus Flight Price Trend Finder   ")
    print("=====================================================")

    if AMADEUS_CLIENT_ID == "YOUR_AMADEUS_CLIENT_ID" or AMADEUS_CLIENT_SECRET == "YOUR_AMADEUS_CLIENT_SECRET":
        print("\n⚠️  WARNING: You haven't set your Amadeus credentials.")
        print("   Please edit this script and replace the placeholder")
        print("   ID and Secret with your actual keys.\n")
        return

    # --- Itinerary to Check ---
    # You can use IATA codes for cities (e.g. NYC) or specific airports (e.g. JFK)
    ORIGIN = "BER"
    DESTINATION = "TPE"

    token = get_amadeus_token()
    if not token:
        print("\nCould not proceed without an API token. Please check your credentials.")
        return

    results = find_cheapest_dates(token, ORIGIN, DESTINATION)
    display_cheapest_month(results, ORIGIN, DESTINATION)

if __name__ == "__main__":
    main()
