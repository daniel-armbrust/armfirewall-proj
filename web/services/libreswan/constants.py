from __future__ import annotations

from core.constants import LOG_DIR


AUTO_VALUES = {"add", "ondemand", "route", "start", "ignore"}
YES_NO_VALUES = {"yes", "no"}
IKEV2_VALUES = {"no", "never", "permit", "propose", "insist", "yes"}
ENCAPSULATION_VALUES = {"yes", "no", "auto"}

LIBRESWAN_STDOUT_LOG_PATH = LOG_DIR / "libreswan.out.log"
LIBRESWAN_STDERR_LOG_PATH = LOG_DIR / "libreswan.err.log"
LIBRESWAN_LOG_FILES = (
    ("stdout", LIBRESWAN_STDOUT_LOG_PATH),
    ("stderr", LIBRESWAN_STDERR_LOG_PATH),
)

CONNECTION_FIELDS = (
    "conn_name",
    "description",
    "enabled",
    "left_addr",
    "left_id",
    "right_addr",
    "authby",
    "shared_secret",
    "leftsubnet",
    "rightsubnet",
    "auto",
    "mark",
    "vti_interface",
    "vti_addr",
    "vti_mtu",
    "vti_routing",
    "ikev2",
    "ike",
    "phase2alg",
    "encapsulation",
    "ikelifetime",
    "salifetime",
)
