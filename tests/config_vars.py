cfg = {
    "bgp": {
        "asn": 65511,
        "neighbors": [
            {
                "ipaddr": "172.20.12.2",
                "remote_asn": 65512
            },
            {
                "ipaddr": "172.20.13.3",
                "remote_asn": 65513
            }
        ],
        "rid": "1.1.1.1"
    },
    "interfaces": {
        "GigabitEthernet1": {
            "description": "Uplink to CSR-2",
            "ipaddr": "172.20.12.1 255.255.255.0",
            "state": "up"
        },
        "GigabitEthernet2": {
            "description": "Uplink to CSR-3",
            "ipaddr": "172.20.13.1 255.255.255.0",
            "state": "up"
        },
        "Loopback0": {
            "description": "Router ID",
            "ipaddr": "1.1.1.1 255.255.255.255",
            "state": "up"
        }
    }
}
