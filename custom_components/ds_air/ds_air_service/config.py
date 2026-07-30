class Config:
    """Process-local protocol profile selected for the single gateway entry."""

    PROFILE_B611 = "dta117b611"
    PROFILE_C611 = "dta117c611"
    PROFILE_D611 = "dta117d611_verified"

    is_new_version: bool = False
    is_c611: bool = True  # C611 uses the legacy status branch.
    gateway_model: str = "DTA117C611"
    protocol_profile: str = PROFILE_C611
    protocol_version_locked: bool = False

    @classmethod
    def configure_gateway(cls, gateway_model: str):
        """Select a stable wire profile before discovery starts.

        DTA117D611 has been verified against the official-app layout: cmd2/cmd3
        bit 3 is one reserved byte and the extended capability bytes are
        present.  It must not inherit a mutable B/C guess from later generic
        ACK traffic.
        """
        cls.gateway_model = gateway_model
        cls.is_c611 = gateway_model == "DTA117C611"
        if gateway_model == "DTA117D611":
            cls.protocol_profile = cls.PROFILE_D611
            cls.is_new_version = True
            cls.protocol_version_locked = True
        elif gateway_model == "DTA117B611":
            cls.protocol_profile = cls.PROFILE_B611
            cls.is_new_version = False
            cls.protocol_version_locked = False
        elif gateway_model == "DTA117C611":
            cls.protocol_profile = cls.PROFILE_C611
            cls.is_new_version = False
            cls.protocol_version_locked = False
        else:
            raise ValueError(f"unsupported DS-AIR gateway model: {gateway_model}")

    @classmethod
    def observe_protocol_ack(cls, body_version: int):
        """Let legacy B/C profiles lock once; never let ordinary ACKs flap it."""
        if cls.protocol_version_locked:
            return
        cls.is_new_version = body_version == 2
        cls.protocol_version_locked = True
