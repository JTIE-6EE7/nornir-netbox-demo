# nornir-netbox-demo.py

This script uses Netbox as a Source of Truth for Nornir to automate the provisioning, deployment and validation of a demo WAN.

Devices must be added to Netbox with a Primary IP address for management and be accessible via SSH.

JSON provisioning data must be populated in NetBox for each device in the Config Context field.

# Script overview:

* Initialize Nornir/Netbox

* Enable SCP

* Get config variables from Netbox

* Render config files

* Apply Layer 3 configs

* Validate Layer 3 connectivity

* Apply BGP configs

* Validate BGP adjacencies

* Update Netbox data

* Disable SCP / save configs


# Sample Config Context provisioning data for Netbox:

```json
{
    "bgp": {
        "asn": 65511,
        "rid": "1.1.1.1",
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
        "networks": [
            {
                "net": "1.1.1.1",
                "mask": "255.255.255.255"
            },
            {
                "net": "172.20.12.0",
                "mask": "255.255.255.0"
            },
            {
                "net": "172.20.13.0",
                "mask": "255.255.255.0"
            }
        ]
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
```
