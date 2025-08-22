def sea_level_pressure(pressure_hpa, altitude_m):
    """
    Calculate sea-level equivalent pressure from measured pressure and altitude.

    :param pressure_hpa: Measured pressure in hPa (hectopascals)
    :param altitude_m: Altitude above sea level in meters
    :return: Sea-level equivalent pressure in hPa
    """
    # Constants
    T0 = 288.15        # Sea-level standard temperature in K
    L = 0.0065         # Temperature lapse rate in K/m
    exponent = 5.257   # Precomputed constant from gas equation

    # Convert measured pressure to Pa if needed
    pressure_pa = pressure_hpa * 100

    # Apply barometric formula
    p0_pa = pressure_pa * ((1 - (L * altitude_m) / T0) ** -exponent)

    # Convert back to hPa for readability
    return p0_pa / 100


if __name__ == "__main__":
    # Example usage
    measured_pressure = 1007.70  # Example pressure in hPa
    altitude = 13  # Example altitude in meters

    sea_level_pressure_value = sea_level_pressure(measured_pressure, altitude)
    print(f"Sea-level equivalent pressure: {sea_level_pressure_value:.2f} hPa")