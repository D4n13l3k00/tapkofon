"""Ephemeral QR login: keep its secret URL out of HTML, SQLite and logs."""

import asyncio
import contextlib
import io
import logging
import secrets
from typing import TYPE_CHECKING, Any, Literal

import qrcode
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text
from telethon import errors

from .telegram_gateway import QRLoginGateway

if TYPE_CHECKING:
    from .runtime import Runtime


def qr_png(url: str) -> bytes:
    code = qrcode.QRCode(box_size=4, border=4)
    code.add_data(url)
    code.make(fit=True)
    image = code.make_image(fill_color="black", back_color="white")
    output = io.BytesIO()
    image.save(output)
    return output.getvalue()


class WebQR:
    def __init__(self, qr: QRLoginGateway, browser: str):
        self.qr = qr
        self.browser = browser
        self.public_id = secrets.token_hex(8)
        self.status: Literal[
            "waiting", "expired", "password", "authorized", "error"
        ] = "waiting"
        self.user: Any = None
        self.task: asyncio.Task[None] | None = None

    async def monitor(self) -> None:
        try:
            self.user = await self.qr.wait()
            self.status = "authorized"
        except errors.SessionPasswordNeededError:
            self.status = "password"
        except TimeoutError:
            self.status = "expired"
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.status = "error"
            logging.getLogger(__name__).warning(
                "QR login failed: %s", type(error).__name__
            )

    async def cancel(self) -> None:
        if self.task is not None:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task


def print_terminal_qr(console: Console, url: str) -> None:
    code = qrcode.QRCode(border=4)
    code.add_data(url)
    code.make(fit=True)
    if len(code.get_matrix()) + 4 > console.width:
        raise ValueError("Terminal is too narrow for the QR code")
    output = io.StringIO()
    code.print_ascii(out=output, invert=False)
    console.print(
        Panel(
            Text(output.getvalue().rstrip("\n"), style="black on white"),
            title="Telegram QR",
            border_style="cyan",
            padding=0,
            expand=False,
        )
    )


async def terminal_qr_login(runtime: "Runtime", console: Console) -> None:
    client = await runtime.connect()
    if await client.is_user_authorized():
        return
    console.print(
        "В Telegram на другом устройстве: [cyan]Настройки → Устройства → Подключить устройство[/cyan]."
    )
    while True:
        qr = await client.qr_login()
        task = asyncio.create_task(qr.wait())
        # Register Telethon's update listener before anyone can scan the code.
        await asyncio.sleep(0)
        try:
            print_terminal_qr(console, qr.url)
            with console.status("Ожидаем сканирование QR…"):
                await task
            return
        except TimeoutError:
            console.print("[yellow]QR истёк. Создаём новый код.[/yellow]")
        except errors.SessionPasswordNeededError:
            for _ in range(3):
                password = await asyncio.to_thread(
                    Prompt.ask,
                    "Облачный пароль Telegram",
                    password=True,
                    console=console,
                )
                try:
                    await client.sign_in(password=password)
                    return
                except errors.PasswordHashInvalidError:
                    console.print("[red]Неверный облачный пароль.[/red]")
            raise RuntimeError("Telegram password attempts exhausted") from None
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
