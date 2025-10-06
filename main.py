import requests
import os
from collections import defaultdict
import datetime

# --- Configuration ---
# Get your credentials from the Amadeus for Developers portal:
# https://developers.amadeus.com/
AMADEUS_CLIENT_ID = os.environ.get("api-key", "YOUR_AMADEUS_CLIENT_ID")
AMADEUS_CLIENT_SECRET = os.environ.get("api-secret", "YOUR_AMADEUS_CLIENT_SECRET")

def get_airline_name_from_api(token, carrier_code):
    """
    Fetches airline name from Amadeus API using the airline code.
    
    Args:
        token (str): The Amadeus API access token
        carrier_code (str): The airline IATA code
        
    Returns:
        str: Full airline name or code if not found
    """
    if not carrier_code or carrier_code in airline_cache:
        return airline_cache.get(carrier_code, carrier_code)
    
    headers = {
        "Authorization": f"Bearer {token}"
    }
    params = {
        "airlineCodes": carrier_code
    }
    
    try:
        response = requests.get(AIRLINES_URL, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        airlines = data.get("data", [])
        if airlines:
            airline = airlines[0]
            # Use business name if available, otherwise common name
            airline_name = airline.get("businessName") or airline.get("commonName", carrier_code)
            airline_cache[carrier_code] = airline_name
            return airline_name
        else:
            # If not found in API, cache the code itself
            airline_cache[carrier_code] = carrier_code
            return carrier_code
            
    except requests.exceptions.RequestException as e:
        print(f"⚠️  Could not fetch airline name for {carrier_code}: {e}")
        # If API fails, just return the code
        return carrier_code

def get_airline_name(segment, token=None):
    """
    Gets the full airline name from a flight segment.
    
    Args:
        segment (dict): Flight segment data from Amadeus API
        token (str): The Amadeus API access token (optional)
        
    Returns:
        str: Full airline name or code if not found
    """
    carrier_code = segment.get("carrierCode", "")
    
    if not carrier_code:
        return "Unknown"
    
    # First try to get the airline name from the API response
    airline_name = segment.get("carrier", "")
    if airline_name and airline_name != carrier_code:
        return airline_name
    
    # If we have a token, try to fetch from Amadeus API
    if token:
        return get_airline_name_from_api(token, carrier_code)
    
    # If no token provided, just return the code
    return carrier_code

# Amadeus API endpoint URLs (using the test environment)
TOKEN_URL = "https://test.api.amadeus.com/v1/security/oauth2/token"
# Flight Offers Search API supports connecting flights
FLIGHT_OFFERS_URL = "https://test.api.amadeus.com/v2/shopping/flight-offers"
# Airline information endpoint
AIRLINES_URL = "https://test.api.amadeus.com/v1/reference-data/airlines"

# Cache for airline names to avoid repeated API calls
airline_cache = {}

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

def find_cheapest_flights(token, origin, destination, departure_date, max_connections=2):
    """
    Searches for the cheapest flights for a given route and date, including connecting flights.

    Args:
        token (str): The Amadeus API access token.
        origin (str): The origin airport/city code (e.g., "MAD").
        destination (str): The destination airport/city code (e.g., "BOS").
        departure_date (str): The departure date in YYYY-MM-DD format.
        max_connections (int): Maximum number of connections allowed (0 for direct only, 1-2 for connecting flights).

    Returns:
        list: A list of flight offers, or an empty list if an error occurs.
    """
    print(f"\n✈️  Finding cheapest flights for: {origin} -> {destination} on {departure_date}...")
    print(f"   (Including flights with up to {max_connections} connections)")
    
    headers = {
        "Authorization": f"Bearer {token}"
    }
    params = {
        "originLocationCode": origin,
        "destinationLocationCode": destination,
        "departureDate": departure_date,
        "adults": 1,
        "max": 10,  # Limit results for performance
        "currencyCode": "EUR"
    }

    try:
        response = requests.get(FLIGHT_OFFERS_URL, headers=headers, params=params)
        response.raise_for_status()
        print("✅ Flight offers received!")
        data = response.json()
        offers = data.get("data", [])
        
        # Filter offers by number of connections
        filtered_offers = []
        for offer in offers:
            itinerary = offer.get("itineraries", [{}])[0]
            segments = itinerary.get("segments", [])
            connections = len(segments) - 1  # Number of connections = segments - 1
            
            if connections <= max_connections:
                filtered_offers.append(offer)
        
        print(f"   Found {len(filtered_offers)} flights with {max_connections} or fewer connections")
        return filtered_offers
        
    except requests.exceptions.RequestException as e:
        print(f"❌ An error occurred while searching for flights: {e}")
        if e.response:
            print(f"   Error details: {e.response.json()}")
        return []

def search_flights_by_month(token, origin, destination, max_connections=2):
    """
    Searches for the cheapest flights across multiple months, including connecting flights.

    Args:
        token (str): The Amadeus API access token.
        origin (str): The origin airport/city code.
        destination (str): The destination airport/city code.
        max_connections (int): Maximum number of connections allowed.

    Returns:
        dict: A dictionary with month keys and cheapest flight offers.
    """
    print(f"\n🔍 Searching for cheapest flights across multiple months...")
    
    cheapest_by_month = {}
    overall_cheapest_offer = None
    
    # Search for the next 12 months
    current_date = datetime.datetime.now()
    
    for month_offset in range(12):
        search_date = current_date + datetime.timedelta(days=30 * month_offset)
        date_str = search_date.strftime("%Y-%m-%d")
        
        print(f"   Searching {date_str}...")
        offers = find_cheapest_flights(token, origin, destination, date_str, max_connections)
        
        if offers:
            # Find the cheapest offer for this date
            cheapest_offer = min(offers, key=lambda x: float(x.get("price", {}).get("total", float('inf'))))
            
            try:
                price = float(cheapest_offer.get("price", {}).get("total"))
                month_key = search_date.strftime("%Y-%m")
                
                # Check for overall cheapest
                if overall_cheapest_offer is None or price < float(overall_cheapest_offer.get("price", {}).get("total")):
                    overall_cheapest_offer = cheapest_offer
                
                # Check for cheapest in that month
                if month_key not in cheapest_by_month or price < float(cheapest_by_month[month_key].get("price", {}).get("total")):
                    cheapest_by_month[month_key] = cheapest_offer
                    
            except (ValueError, TypeError, KeyError):
                continue
    
    return cheapest_by_month, overall_cheapest_offer

def display_cheapest_month(cheapest_by_month, overall_cheapest_offer, origin, destination, token=None):
    """
    Displays the cheapest flight options per month and overall.

    Args:
        cheapest_by_month (dict): Dictionary with month keys and cheapest offers.
        overall_cheapest_offer (dict): The overall cheapest offer.
        origin (str): The origin airport/city code.
        destination (str): The destination airport/city code.
    """
    if not cheapest_by_month:
        print("\n😕 No flight results found. The test API might not have data for this route.")
        return

    print(f"\n--- Cheapest Flight per Month ({origin} -> {destination}) ---")
    sorted_months = sorted(cheapest_by_month.keys())
    
    for month in sorted_months:
        offer = cheapest_by_month[month]
        price = offer.get("price", {}).get("total")
        
        # Get departure date from the first segment
        itinerary = offer.get("itineraries", [{}])[0]
        segments = itinerary.get("segments", [])
        if segments:
            departure_date = segments[0].get("departure", {}).get("at", "").split("T")[0]
            month_name = datetime.datetime.strptime(departure_date, "%Y-%m-%d").strftime("%B %Y")
            
            # Count connections and get airline info
            connections = len(segments) - 1
            connection_text = "Direct" if connections == 0 else f"{connections} connection{'s' if connections > 1 else ''}"
            
            # Get airline information from the first segment
            first_segment = segments[0]
            airline_name = get_airline_name(first_segment, token)
            
            print(f"  - {month_name+':':<15} ${price} on {departure_date} ({connection_text}) - {airline_name}")

    if overall_cheapest_offer:
        print("\n--- 🏆 Overall Cheapest Trip Found ---")
        price = overall_cheapest_offer.get("price", {}).get("total")
        
        # Get flight details
        itinerary = overall_cheapest_offer.get("itineraries", [{}])[0]
        segments = itinerary.get("segments", [])
        if segments:
            departure_date = segments[0].get("departure", {}).get("at", "").split("T")[0]
            connections = len(segments) - 1
            connection_text = "Direct" if connections == 0 else f"{connections} connection{'s' if connections > 1 else ''}"
            
            # Get airline information
            first_segment = segments[0]
            airline_name = get_airline_name(first_segment, token)
            
            print(f"  💰 Price: ${price}")
            print(f"  📅 Date:  {departure_date}")
            print(f"  🔄 Route:  {connection_text}")
            print(f"  ✈️  Airline: {airline_name}")
            
            # Show route details for connecting flights
            if connections > 0:
                print(f"  🛫 Route details:")
                for i, segment in enumerate(segments):
                    departure = segment.get("departure", {})
                    arrival = segment.get("arrival", {})
                    carrier = segment.get("carrierCode", "Unknown")
                    flight_number = segment.get("number", "")
                    
                    dep_airport = departure.get("iataCode", "")
                    arr_airport = arrival.get("iataCode", "")
                    dep_time = departure.get("at", "").split("T")[1][:5] if departure.get("at") else ""
                    arr_time = arrival.get("at", "").split("T")[1][:5] if arrival.get("at") else ""
                    
                    if i == 0:
                        print(f"     {dep_airport} → {arr_airport} {carrier}{flight_number} {dep_time}-{arr_time}")
                    else:
                        print(f"     {dep_airport} → {arr_airport} {carrier}{flight_number} {dep_time}-{arr_time}")
    
    print("\n-----------------------------------------")
    print("(Note: This is test data and cannot be booked.)")

def main():
    print("=====================================================")
    print("   Amadeus Flight Price Trend Finder   ")
    print("   (Now with connecting flights support!)")
    print("=====================================================")

    if AMADEUS_CLIENT_ID == "YOUR_AMADEUS_CLIENT_ID" or AMADEUS_CLIENT_SECRET == "YOUR_AMADEUS_CLIENT_SECRET":
        print("\n⚠️  WARNING: You haven't set your Amadeus credentials.")
        print("   Please edit this script and replace the placeholder")
        print("   ID and Secret with your actual keys.\n")
        return

    # --- Itinerary to Check ---
    # You can use IATA codes for cities (e.g. NYC) or specific airports (e.g. JFK)
    ORIGIN = os.environ.get("origin")   
    DESTINATION = os.environ.get("destination")
    MAX_CONNECTIONS = int(os.environ.get("max_connections"))  # Allow up to 2 connections (0 = direct only, 1 = 1 connection, 2 = 2 connections)

    token = get_amadeus_token()
    if not token:
        print("\nCould not proceed without an API token. Please check your credentials.")
        return

    cheapest_by_month, overall_cheapest = search_flights_by_month(token, ORIGIN, DESTINATION, MAX_CONNECTIONS)
    display_cheapest_month(cheapest_by_month, overall_cheapest, ORIGIN, DESTINATION, token)

if __name__ == "__main__":
    main()
