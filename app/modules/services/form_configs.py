"""
Dynamic service form configurations for all 10 Pakistani vehicle service types.
Each config defines the extra fields a provider must fill in beyond the base
service fields (name, description, basePrice, pricePerKm, pricePerHour).

Field types: number | text | dropdown | multi_select | toggle | radio
"""

SERVICE_FORM_CONFIGS: dict = {

    "sand_trolley": {
        "label": "Sand Trolley",
        "sections": [
            {
                "title": "Truck & Material",
                "fields": [
                    {
                        "key": "capacityTons",
                        "label": "Truck Capacity (Tons)",
                        "type": "number",
                        "hint": "e.g. 10",
                        "unit": "tons",
                        "required": True,
                    },
                    {
                        "key": "materialType",
                        "label": "Sand Type",
                        "type": "dropdown",
                        "options": ["River Sand", "Pit Sand", "Sea Sand", "Desert Sand", "Mixed"],
                        "required": True,
                    },
                ],
            },
            {
                "title": "Trip Pricing",
                "fields": [
                    {
                        "key": "pricePerTrip",
                        "label": "Price Per Trip (Rs)",
                        "type": "number",
                        "hint": "Base fare for one full trip",
                        "unit": "Rs",
                        "required": True,
                    },
                    {
                        "key": "includedKm",
                        "label": "Included KM per Trip",
                        "type": "number",
                        "hint": "Distance covered in base trip price",
                        "unit": "km",
                        "required": False,
                    },
                    {
                        "key": "extraKmCharge",
                        "label": "Extra KM Charge (Rs/km)",
                        "type": "number",
                        "hint": "Charge per km beyond included distance",
                        "unit": "Rs/km",
                        "required": False,
                    },
                ],
            },
            {
                "title": "Service Options",
                "fields": [
                    {
                        "key": "loadingIncluded",
                        "label": "Loading Included",
                        "type": "toggle",
                        "defaultValue": False,
                    },
                    {
                        "key": "unloadingIncluded",
                        "label": "Unloading Included",
                        "type": "toggle",
                        "defaultValue": False,
                    },
                ],
            },
        ],
    },

    "bricks_trolley": {
        "label": "Bricks Trolley",
        "sections": [
            {
                "title": "Capacity",
                "fields": [
                    {
                        "key": "capacityThousands",
                        "label": "Capacity (Thousands of Bricks)",
                        "type": "number",
                        "hint": "e.g. 5 for 5,000 bricks",
                        "unit": "k bricks",
                        "required": True,
                    },
                ],
            },
            {
                "title": "Pricing",
                "fields": [
                    {
                        "key": "pricePerThousandBricks",
                        "label": "Price per 1,000 Bricks (Rs)",
                        "type": "number",
                        "hint": "Transport charge per thousand bricks",
                        "unit": "Rs/1k",
                        "required": True,
                    },
                    {
                        "key": "pricePerKmTransport",
                        "label": "Transport Charge (Rs/km)",
                        "type": "number",
                        "hint": "Distance-based charge",
                        "unit": "Rs/km",
                        "required": False,
                    },
                ],
            },
            {
                "title": "Service Options",
                "fields": [
                    {
                        "key": "stackingIncluded",
                        "label": "Stacking at Site Included",
                        "type": "toggle",
                        "defaultValue": False,
                    },
                    {
                        "key": "loadingIncluded",
                        "label": "Loading Included",
                        "type": "toggle",
                        "defaultValue": False,
                    },
                ],
            },
        ],
    },

    "tractor": {
        "label": "Tractor",
        "sections": [
            {
                "title": "Available Implements",
                "fields": [
                    {
                        "key": "availableImplements",
                        "label": "Implements Offered",
                        "type": "multi_select",
                        "options": [
                            "Rotavator",
                            "Disc Harrow",
                            "Cultivator",
                            "Plough",
                            "Laser Leveler",
                            "Ripper",
                            "Thresher",
                            "Subsoiler",
                        ],
                        "required": True,
                    },
                ],
            },
            {
                "title": "Pricing",
                "fields": [
                    {
                        "key": "pricePerAcre",
                        "label": "Price per Acre (Rs)",
                        "type": "number",
                        "hint": "Standard per-acre charge",
                        "unit": "Rs/acre",
                        "required": True,
                    },
                    {
                        "key": "pricePerHourHire",
                        "label": "Hourly Hire Rate (Rs/hr)",
                        "type": "number",
                        "hint": "For hourly booking (optional)",
                        "unit": "Rs/hr",
                        "required": False,
                    },
                    {
                        "key": "minimumAcres",
                        "label": "Minimum Acres per Visit",
                        "type": "number",
                        "hint": "e.g. 2",
                        "unit": "acres",
                        "required": False,
                    },
                ],
            },
            {
                "title": "Fuel & Travel",
                "fields": [
                    {
                        "key": "fuelIncluded",
                        "label": "Fuel Cost Included in Price",
                        "type": "toggle",
                        "defaultValue": False,
                    },
                    {
                        "key": "mobilizationCharge",
                        "label": "Mobilization Charge (Rs/km)",
                        "type": "number",
                        "hint": "Travel-to-site charge per km",
                        "unit": "Rs/km",
                        "required": False,
                    },
                ],
            },
        ],
    },

    "harvester": {
        "label": "Harvester",
        "sections": [
            {
                "title": "Crop Specialization",
                "fields": [
                    {
                        "key": "cropTypes",
                        "label": "Crops Harvested",
                        "type": "multi_select",
                        "options": ["Wheat", "Rice", "Corn", "Sugarcane", "Sunflower", "Cotton"],
                        "required": True,
                    },
                ],
            },
            {
                "title": "Pricing",
                "fields": [
                    {
                        "key": "pricePerAcre",
                        "label": "Price per Acre (Rs)",
                        "type": "number",
                        "hint": "Standard harvesting rate",
                        "unit": "Rs/acre",
                        "required": True,
                    },
                    {
                        "key": "minimumAcres",
                        "label": "Minimum Acres",
                        "type": "number",
                        "hint": "Minimum booking size",
                        "unit": "acres",
                        "required": False,
                    },
                    {
                        "key": "mobilizationCharge",
                        "label": "Mobilization Charge (Rs/km)",
                        "type": "number",
                        "hint": "Travel-to-field charge per km",
                        "unit": "Rs/km",
                        "required": False,
                    },
                ],
            },
            {
                "title": "Fuel",
                "fields": [
                    {
                        "key": "fuelIncluded",
                        "label": "Fuel Cost Included in Price",
                        "type": "toggle",
                        "defaultValue": False,
                    },
                ],
            },
        ],
    },

    "crane": {
        "label": "Crane",
        "sections": [
            {
                "title": "Specifications",
                "fields": [
                    {
                        "key": "liftingCapacityTons",
                        "label": "Lifting Capacity (Tons)",
                        "type": "number",
                        "hint": "Maximum safe working load",
                        "unit": "tons",
                        "required": True,
                    },
                    {
                        "key": "boomLengthM",
                        "label": "Boom Length (Meters)",
                        "type": "number",
                        "hint": "Maximum reach",
                        "unit": "m",
                        "required": False,
                    },
                ],
            },
            {
                "title": "Pricing",
                "fields": [
                    {
                        "key": "pricePerHour",
                        "label": "Hourly Rate (Rs)",
                        "type": "number",
                        "hint": "Standard hourly charge",
                        "unit": "Rs/hr",
                        "required": True,
                    },
                    {
                        "key": "minimumHours",
                        "label": "Minimum Hours",
                        "type": "number",
                        "hint": "e.g. 4",
                        "unit": "hrs",
                        "required": False,
                    },
                    {
                        "key": "mobilizationCharge",
                        "label": "Mobilization Charge (Rs/km)",
                        "type": "number",
                        "hint": "Travel-to-site charge",
                        "unit": "Rs/km",
                        "required": False,
                    },
                ],
            },
            {
                "title": "Packages",
                "fields": [
                    {
                        "key": "packageAvailable",
                        "label": "Shift Packages Available",
                        "type": "toggle",
                        "defaultValue": False,
                    },
                    {
                        "key": "package4hPrice",
                        "label": "4-Hour Package Price (Rs)",
                        "type": "number",
                        "hint": "Discounted 4-hour rate",
                        "unit": "Rs",
                        "required": False,
                        "showWhen": "packageAvailable",
                        "showWhenValue": True,
                    },
                    {
                        "key": "package8hPrice",
                        "label": "8-Hour Package Price (Rs)",
                        "type": "number",
                        "hint": "Discounted 8-hour / shift rate",
                        "unit": "Rs",
                        "required": False,
                        "showWhen": "packageAvailable",
                        "showWhenValue": True,
                    },
                ],
            },
        ],
    },

    "loader": {
        "label": "Loader",
        "sections": [
            {
                "title": "Equipment",
                "fields": [
                    {
                        "key": "bucketCapacityTons",
                        "label": "Bucket Capacity (Tons)",
                        "type": "number",
                        "hint": "Loader bucket size",
                        "unit": "tons",
                        "required": True,
                    },
                    {
                        "key": "materialTypes",
                        "label": "Materials Handled",
                        "type": "multi_select",
                        "options": ["Sand", "Bricks", "Gravel", "Soil", "Debris", "Coal", "Grain"],
                        "required": False,
                    },
                ],
            },
            {
                "title": "Pricing",
                "fields": [
                    {
                        "key": "pricePerHour",
                        "label": "Hourly Rate (Rs)",
                        "type": "number",
                        "hint": "Standard hourly charge",
                        "unit": "Rs/hr",
                        "required": True,
                    },
                    {
                        "key": "minimumHours",
                        "label": "Minimum Hours",
                        "type": "number",
                        "hint": "e.g. 2",
                        "unit": "hrs",
                        "required": False,
                    },
                ],
            },
            {
                "title": "Fuel",
                "fields": [
                    {
                        "key": "fuelIncluded",
                        "label": "Fuel Cost Included",
                        "type": "toggle",
                        "defaultValue": False,
                    },
                ],
            },
        ],
    },

    "dumper": {
        "label": "Dumper",
        "sections": [
            {
                "title": "Capacity",
                "fields": [
                    {
                        "key": "capacityTons",
                        "label": "Load Capacity (Tons)",
                        "type": "number",
                        "hint": "Maximum payload",
                        "unit": "tons",
                        "required": True,
                    },
                ],
            },
            {
                "title": "Pricing Model",
                "fields": [
                    {
                        "key": "pricingModel",
                        "label": "Pricing Mode",
                        "type": "radio",
                        "options": [
                            {"value": "per_trip", "label": "Per Trip"},
                            {"value": "per_hour", "label": "Per Hour"},
                        ],
                        "defaultValue": "per_trip",
                        "required": True,
                    },
                    {
                        "key": "pricePerTrip",
                        "label": "Price Per Trip (Rs)",
                        "type": "number",
                        "hint": "Flat fare for one trip",
                        "unit": "Rs",
                        "required": False,
                        "showWhen": "pricingModel",
                        "showWhenValue": "per_trip",
                    },
                    {
                        "key": "pricePerHour",
                        "label": "Hourly Rate (Rs)",
                        "type": "number",
                        "hint": "Charge per hour of work",
                        "unit": "Rs/hr",
                        "required": False,
                        "showWhen": "pricingModel",
                        "showWhenValue": "per_hour",
                    },
                    {
                        "key": "includedKm",
                        "label": "Included KM (per trip)",
                        "type": "number",
                        "hint": "Distance included in trip price",
                        "unit": "km",
                        "required": False,
                        "showWhen": "pricingModel",
                        "showWhenValue": "per_trip",
                    },
                    {
                        "key": "extraKmCharge",
                        "label": "Extra KM Charge (Rs/km)",
                        "type": "number",
                        "hint": "Beyond included distance",
                        "unit": "Rs/km",
                        "required": False,
                        "showWhen": "pricingModel",
                        "showWhenValue": "per_trip",
                    },
                ],
            },
        ],
    },

    "excavator": {
        "label": "Excavator",
        "sections": [
            {
                "title": "Equipment",
                "fields": [
                    {
                        "key": "bucketSizeCubicM",
                        "label": "Bucket Size (m³)",
                        "type": "number",
                        "hint": "e.g. 0.5",
                        "unit": "m³",
                        "required": True,
                    },
                ],
            },
            {
                "title": "Pricing",
                "fields": [
                    {
                        "key": "pricePerHour",
                        "label": "Hourly Rate (Rs)",
                        "type": "number",
                        "hint": "Standard hourly charge",
                        "unit": "Rs/hr",
                        "required": True,
                    },
                    {
                        "key": "minimumHours",
                        "label": "Minimum Hours",
                        "type": "number",
                        "hint": "e.g. 4",
                        "unit": "hrs",
                        "required": False,
                    },
                ],
            },
            {
                "title": "Packages",
                "fields": [
                    {
                        "key": "packageAvailable",
                        "label": "Shift Packages Available",
                        "type": "toggle",
                        "defaultValue": False,
                    },
                    {
                        "key": "package4hPrice",
                        "label": "4-Hour Package (Rs)",
                        "type": "number",
                        "unit": "Rs",
                        "required": False,
                        "showWhen": "packageAvailable",
                        "showWhenValue": True,
                    },
                    {
                        "key": "package8hPrice",
                        "label": "8-Hour Package (Rs)",
                        "type": "number",
                        "unit": "Rs",
                        "required": False,
                        "showWhen": "packageAvailable",
                        "showWhenValue": True,
                    },
                ],
            },
            {
                "title": "Fuel",
                "fields": [
                    {
                        "key": "fuelIncluded",
                        "label": "Fuel Cost Included",
                        "type": "toggle",
                        "defaultValue": False,
                    },
                ],
            },
        ],
    },

    "concrete_mixer": {
        "label": "Concrete Mixer",
        "sections": [
            {
                "title": "Equipment",
                "fields": [
                    {
                        "key": "drumCapacityBags",
                        "label": "Drum Capacity (Bags of Cement)",
                        "type": "number",
                        "hint": "e.g. 5",
                        "unit": "bags",
                        "required": True,
                    },
                ],
            },
            {
                "title": "Pricing Model",
                "fields": [
                    {
                        "key": "pricingModel",
                        "label": "Pricing Mode",
                        "type": "radio",
                        "options": [
                            {"value": "per_bag", "label": "Per Bag"},
                            {"value": "per_hour", "label": "Per Hour"},
                            {"value": "per_day", "label": "Per Day"},
                        ],
                        "defaultValue": "per_hour",
                        "required": True,
                    },
                    {
                        "key": "pricePerBag",
                        "label": "Price Per Bag (Rs)",
                        "type": "number",
                        "hint": "Mixing charge per cement bag",
                        "unit": "Rs/bag",
                        "required": False,
                        "showWhen": "pricingModel",
                        "showWhenValue": "per_bag",
                    },
                    {
                        "key": "pricePerHour",
                        "label": "Hourly Rate (Rs)",
                        "type": "number",
                        "hint": "Charge per hour of operation",
                        "unit": "Rs/hr",
                        "required": False,
                        "showWhen": "pricingModel",
                        "showWhenValue": "per_hour",
                    },
                    {
                        "key": "pricePerDay",
                        "label": "Daily Rate (Rs)",
                        "type": "number",
                        "hint": "Full day (8 hrs) charge",
                        "unit": "Rs/day",
                        "required": False,
                        "showWhen": "pricingModel",
                        "showWhenValue": "per_day",
                    },
                    {
                        "key": "mobilizationCharge",
                        "label": "Mobilization Charge (Rs/km)",
                        "type": "number",
                        "hint": "Travel-to-site charge",
                        "unit": "Rs/km",
                        "required": False,
                    },
                ],
            },
        ],
    },

    "water_tanker": {
        "label": "Water Tanker",
        "sections": [
            {
                "title": "Tanker Specs",
                "fields": [
                    {
                        "key": "capacityLitres",
                        "label": "Tank Capacity",
                        "type": "dropdown",
                        "options": ["3,000 L", "5,000 L", "10,000 L", "15,000 L", "20,000 L"],
                        "required": True,
                    },
                    {
                        "key": "waterType",
                        "label": "Water Type",
                        "type": "dropdown",
                        "options": ["Fresh Water", "Filtered Water", "Construction Water", "Drinking Water"],
                        "required": True,
                    },
                ],
            },
            {
                "title": "Pricing",
                "fields": [
                    {
                        "key": "pricePerTrip",
                        "label": "Price Per Trip (Rs)",
                        "type": "number",
                        "hint": "Base delivery charge",
                        "unit": "Rs",
                        "required": True,
                    },
                    {
                        "key": "includedKm",
                        "label": "Included KM",
                        "type": "number",
                        "hint": "Distance in base trip price",
                        "unit": "km",
                        "required": False,
                    },
                    {
                        "key": "extraKmCharge",
                        "label": "Extra KM Charge (Rs/km)",
                        "type": "number",
                        "hint": "Beyond included distance",
                        "unit": "Rs/km",
                        "required": False,
                    },
                ],
            },
            {
                "title": "Monthly Contract",
                "fields": [
                    {
                        "key": "monthlyContractAvailable",
                        "label": "Monthly Contract Available",
                        "type": "toggle",
                        "defaultValue": False,
                    },
                    {
                        "key": "monthlyContractPrice",
                        "label": "Monthly Contract Price (Rs)",
                        "type": "number",
                        "hint": "Fixed monthly rate",
                        "unit": "Rs/month",
                        "required": False,
                        "showWhen": "monthlyContractAvailable",
                        "showWhenValue": True,
                    },
                    {
                        "key": "tripsPerMonth",
                        "label": "Trips Included per Month",
                        "type": "number",
                        "hint": "No. of deliveries in contract",
                        "unit": "trips",
                        "required": False,
                        "showWhen": "monthlyContractAvailable",
                        "showWhenValue": True,
                    },
                ],
            },
        ],
    },
}


def get_form_config(service_type: str) -> dict | None:
    """Return the form config for a given service type, or None if not found."""
    return SERVICE_FORM_CONFIGS.get(service_type)


def list_service_types() -> list[str]:
    """Return all known service type keys."""
    return list(SERVICE_FORM_CONFIGS.keys())
