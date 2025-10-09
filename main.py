import requests
import os
import datetime
import re # Import regular expressions for parsing duration

# --- Configuration ---
AMADEUS_CLIENT_ID = os.environ.get("amadeus-api-key", "YOUR_AMADEUS_CLIENT_ID")
AMADEUS_CLIENT_SECRET = os.environ.get("amadeus-api-secret", "YOUR_AMADEUS_CLIENT_SECRET")

class FlightFinder:
    """
    A class to find the cheapest flights using a hybrid approach with the Amadeus API.
    It intelligently uses the inspirational Flight Dates API and the live Flight Offers API.
    """
    TOKEN_URL = "https://test.api.amadeus.com/v1/security/oauth2/token"
    FLIGHT_DATES_URL = "https://test.api.amadeus.com/v1/shopping/flight-dates"
    FLIGHT_OFFERS_URL = "https://test.api.amadeus.com/v2/shopping/flight-offers"
    AIRLINES_URL = "https://test.api.amadeus.com/v1/reference-data/airlines"

    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = self._get_token()
        self.airline_cache = {} # Cache for airline names

    def _get_token(self):
        """Retrieves an OAuth2 token from the Amadeus API."""
        if not self.client_id or not self.client_secret or self.client_id == "YOUR_AMADEUS_CLIENT_ID":
            print("❌ ERROR: Amadeus credentials are not set.")
            return None
        
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        body = { "grant_type": "client_credentials", "client_id": self.client_id, "client_secret": self.client_secret }
        try:
            response = requests.post(self.TOKEN_URL, headers=headers, data=body)
            response.raise_for_status()
            print("✅ Access token retrieved successfully.")
            return response.json().get("access_token")
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to get Amadeus token: {e}")
            return None

    def _get_airline_name(self, carrier_code):
        """Fetches and caches an airline's name from its IATA code."""
        if carrier_code in self.airline_cache:
            return self.airline_cache[carrier_code]
        
        headers = {"Authorization": f"Bearer {self.token}"}
        params = {"airlineCodes": carrier_code}
        try:
            response = requests.get(self.AIRLINES_URL, headers=headers, params=params)
            response.raise_for_status()
            data = response.json().get("data", [])
            if data:
                airline_name = data[0].get("businessName", carrier_code)
                self.airline_cache[carrier_code] = airline_name
                return airline_name
        except requests.exceptions.RequestException:
            pass # Fail silently and just return the code
        
        self.airline_cache[carrier_code] = carrier_code
        return carrier_code
    
    def _parse_duration(self, iso_duration):
        """Parses an ISO 8601 duration string (e.g., PT8H30M) into a readable format."""
        if not iso_duration or 'P' not in iso_duration:
            return "N/A"
        
        # Remove the 'P' and 'T' designators
        duration_str = iso_duration.replace("P", "").replace("T", "")
        
        hours, minutes = 0, 0
        
        if 'H' in duration_str:
            h_split = duration_str.split('H')
            hours = int(h_split[0])
            duration_str = h_split[1]
        
        if 'M' in duration_str:
            m_split = duration_str.split('M')
            minutes = int(m_split[0])
            
        return f"{hours}h {minutes}m"


    def _find_candidate_dates(self, origin, destination, search_window_days=180):
        """STEP 1: Use the inspirational API to find the cheapest one-way departure dates."""
        if not self.token: return []

        print(f"\nSTEP 1: 🔍 Finding cheapest departure date candidates for {origin} -> {destination}...")
        start_date = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        end_date = (datetime.date.today() + datetime.timedelta(days=search_window_days)).strftime("%Y-%m-%d")

        params = { "origin": origin, "destination": destination, "departureDate": f"{start_date},{end_date}", "oneWay": "true", "nonStop": "false" }
        headers = {"Authorization": f"Bearer {self.token}"}

        try:
            response = requests.get(self.FLIGHT_DATES_URL, headers=headers, params=params)
            if response.status_code == 404:
                print("  ⚠️  Inspirational API returned 404. This route may not be in the cache.")
                return []
            response.raise_for_status()
            data = response.json().get("data", [])
            print(f"  ✅ Found {len(data)} candidate dates.")
            return data
        except requests.exceptions.RequestException as e:
            print(f"  ❌ An error occurred in Step 1: {e}")
            return []
            
    def _get_live_offer(self, origin, destination, departure_date, min_days, max_days, max_connections):
        """STEP 2 (Helper): Get a live, bookable flight offer for a specific date range."""
        if not self.token: return None

        avg_duration = int((min_days + max_days) / 2)
        return_date_obj = datetime.datetime.strptime(departure_date, "%Y-%m-%d").date() + datetime.timedelta(days=avg_duration)
        return_date = return_date_obj.strftime("%Y-%m-%d")

        params = { 
            "originLocationCode": origin, 
            "destinationLocationCode": destination, 
            "departureDate": departure_date, 
            "returnDate": return_date, 
            "adults": 1, 
            "max": 5,
            # "maxNumberOfConnections": max_connections -> this doesn't work. Shitty Amadeus API
        }
        headers = {"Authorization": f"Bearer {self.token}"}
        
        try:
            response = requests.get(self.FLIGHT_OFFERS_URL, headers=headers, params=params)
            response.raise_for_status()
            offers = response.json().get("data", [])
            return offers[0] if offers else None
        except requests.exceptions.RequestException:
            return None

    def find_cheapest_trip(self, origin, destination, min_days=25, max_days=30, max_connections=2, num_candidates=5):
        """Main method to find the cheapest trip using a hybrid strategy."""
        if not self.token: return None

        candidate_dates = self._find_candidate_dates(origin, destination)
        live_offers = []

        if candidate_dates:
            print(f"\nSTEP 2: ✈️  Getting live offers for the top {num_candidates} candidate dates...")
            top_candidates = sorted(candidate_dates, key=lambda x: float(x['price']['total']))[:num_candidates]
            for candidate in top_candidates:
                offer = self._get_live_offer(origin, destination, candidate['departureDate'], min_days, max_days, max_connections)
                if offer: live_offers.append(offer)
        else:
            print("\n  FALLBACK: Inspirational search failed. Probing live API directly...")
            print(f"STEP 2: ✈️  Probing the first Tuesday of the next 3 months...")
            today = datetime.date.today()
            for i in range(1, 4):
                first_of_month = (today.replace(day=1) + datetime.timedelta(days=31*i)).replace(day=1)
                tuesday = first_of_month + datetime.timedelta(days=(1 - first_of_month.weekday() + 7) % 7)
                offer = self._get_live_offer(origin, destination, tuesday.strftime("%Y-%m-%d"), min_days, max_days, max_connections)
                if offer: live_offers.append(offer)

        if not live_offers:
            print(f"\n😕 No flight results found for {origin} -> {destination}. The test API may not have data for this itinerary.")
            return None
        
        return min(live_offers, key=lambda x: float(x['price']['total']))

    def display_results(self, offer, origin, destination):
        """Prints the final cheapest offer with full segment and airline details."""
        if not offer: return

        print("\n" + "="*60)
        print("🏆 Overall Cheapest Trip Found! 🏆".center(60))
        print("="*60)
        
        price = offer.get("price", {})
        itineraries = offer.get("itineraries", [])
        
        print(f"  Route: {origin} -> {destination}")
        print(f"  💰 Price: {price.get('total')} {price.get('currency')}")
        
        # Extract and display dates
        if itineraries:
            outbound_segments = itineraries[0].get("segments", [])
            inbound_segments = itineraries[1].get("segments", []) if len(itineraries) > 1 else []
            
            if outbound_segments:
                departure_date = datetime.datetime.fromisoformat(outbound_segments[0]['departure']['at']).strftime('%Y-%m-%d')
                print(f"  📅 Departure Date: {departure_date}")
            
            if inbound_segments:
                return_date = datetime.datetime.fromisoformat(inbound_segments[-1]['arrival']['at']).strftime('%Y-%m-%d')
                print(f"  📅 Return Date: {return_date}")
        
        for i, itinerary in enumerate(itineraries):
            journey = "➡️  Outbound" if i == 0 else "⬅️  Inbound"
            segments = itinerary.get("segments", [])
            if not segments: continue

            # Parse and display total duration
            duration_iso = itinerary.get("duration", "")
            duration_formatted = self._parse_duration(duration_iso)

            primary_airline = self._get_airline_name(segments[0]['carrierCode'])
            connections = len(segments) - 1
            connection_text = "Direct" if connections == 0 else f"{connections} connection{'s' if connections > 1 else ''}"
            
            print(f"\n  {journey} ({connection_text} | 🕒 Total Duration: {duration_formatted})")
            print(f"    ✈️  Airline: {primary_airline}")
            print(f"    🛫 Route Details:")
            
            for segment in segments:
                dep = segment['departure']
                arr = segment['arrival']
                airline = self._get_airline_name(segment['carrierCode'])
                flight_num = f"{segment['carrierCode']}{segment['number']}"
                
                dep_time = datetime.datetime.fromisoformat(dep['at']).strftime('%H:%M')
                arr_time = datetime.datetime.fromisoformat(arr['at']).strftime('%H:%M')
                
                print(f"      {dep['iataCode']} ({dep_time}) → {arr['iataCode']} ({arr_time})  |  {flight_num} ({airline})")

        print("\n" + "="*60)


def main():
    """Main function to run the flight finder."""
    print("==========================================")
    print("   Amadeus Hybrid Flight Finder   ")
    print("==========================================")
    
    ORIGIN = os.environ.get("origin", "BER")
    DESTINATION = os.environ.get("destination", "PDX")
    MIN_TRIP_DAYS = int(os.environ.get("min_trip_days", "25"))
    MAX_TRIP_DAYS = int(os.environ.get("max_trip_days", "30"))
    MAX_CONNECTIONS = int(os.environ.get("max_connections", "2"))

    finder = FlightFinder(AMADEUS_CLIENT_ID, AMADEUS_CLIENT_SECRET)
    if finder.token:
        cheapest_trip = finder.find_cheapest_trip(
            origin=ORIGIN, destination=DESTINATION,
            min_days=MIN_TRIP_DAYS, max_days=MAX_TRIP_DAYS,
            max_connections=MAX_CONNECTIONS
        )
        finder.display_results(cheapest_trip, ORIGIN, DESTINATION)

if __name__ == "__main__":
    main()