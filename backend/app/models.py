from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, model_validator

PumpId = Literal["amarelo", "vermelho", "verde", "azul"]
ConnectionMode = Literal["auto", "wifi", "serial", "simulator"]
PrepState = Literal["idle", "dispensing", "completed", "stopped", "error"]


class PumpConfig(BaseModel):
    id: PumpId
    label: str
    ingredient: str
    description: str
    gpio: int
    flow_rate_ml_s: float = Field(gt=1.0, le=200.0)
    color_hex: str
    is_mixer: bool = False


class PumpUpdateRequest(BaseModel):
    ingredient: str | None = Field(default=None, min_length=2, max_length=50)
    description: str | None = Field(default=None, max_length=120)
    flow_rate_ml_s: float | None = Field(default=None, gt=1.0, le=200.0)


class DoseStep(BaseModel):
    pump: PumpId
    ml: float = Field(gt=0, le=500)
    pause_ms: int = Field(default=1000, ge=0, le=10000)


class DrinkRecipe(BaseModel):
    id: str
    code: str
    name: str
    subtitle: str
    description: str
    category: str
    badge: str
    accent_from: str
    accent_to: str
    glass_color: str
    steps: list[DoseStep]
    total_ml: float = 0.0
    estimated_seconds: float = 0.0


class CustomDrinkRequest(BaseModel):
    name: str = Field(default="Mix Personalizado", min_length=1, max_length=40)
    amarelo: float = Field(default=0, ge=0, le=450)
    vermelho: float = Field(default=0, ge=0, le=450)
    verde: float = Field(default=0, ge=0, le=450)
    azul: float = Field(default=0, ge=0, le=450)

    @model_validator(mode="after")
    def validate_total_volume(self) -> "CustomDrinkRequest":
        total = self.amarelo + self.vermelho + self.verde + self.azul
        if total < 10:
            raise ValueError("Selecione pelo menos 10 ml no total para preparar o drink.")
        if total > 450:
            raise ValueError("O volume máximo de segurança por copo é de 450 ml.")
        return self


class ConnectionConfig(BaseModel):
    mode: ConnectionMode = "auto"
    esp32_host: str = "bartender.local"
    esp32_port: int = Field(default=80, ge=1, le=65535)
    serial_port: str = "COM3"
    serial_baud: int = 115200


class PreparationStatus(BaseModel):
    state: PrepState = "idle"
    drink_id: str | None = None
    drink_name: str | None = None
    progress: int = Field(default=0, ge=0, le=100)
    current_pump: PumpId | None = None
    current_step_index: int = 0
    total_steps: int = 0
    message: str = "Pronto para preparar seu próximo drink"
    transport: Literal["wifi", "serial", "simulator"] | None = None
    elapsed_seconds: float = 0.0
    total_seconds: float = 0.0


class HardwareHealth(BaseModel):
    mode: ConnectionMode
    active_transport: Literal["wifi", "serial", "simulator", "disconnected"]
    wifi_reachable: bool = False
    wifi_ip: str | None = None
    wifi_rssi: int | None = None
    serial_connected: bool = False
    available_serial_ports: list[str] = []
    esp32_host: str
    esp32_port: int
    serial_port: str
    serial_baud: int
    detail: str = ""


class SystemSnapshot(BaseModel):
    status: PreparationStatus
    hardware: HardwareHealth

