import pytest

import nornir_netbox_demo 
from nornir import InitNornir



# initialize The Norn
nr = InitNornir(
    inventory={
        "plugin": "nornir.plugins.inventory.simple.SimpleInventory",
        "options": {
            "host_file": "test_hosts.yaml",
            "group_file": "test_groups.yaml",
            "defaults_file": "test_defaults.yaml",
        },
    },
)



def test_interface_jinja():
    pass




