"""Public IP address lookup."""
import ipaddress

from app.core.schemas import Input, UserError
from app.core.tool import Tool

tool = Tool("ipinfo", title="IP lookup", emoji="🌐", description="Where does an IP address live?")

IP = r"\d{1,3}(?:\.\d{1,3}){3}"


@tool.feature(
    "lookup", repeat="reuse", description="Location and owner of a public IP address",
    phrases=["{ip}", "ip {ip}", "ipinfo {ip}", "ip address {ip}", "whois {ip}", "where is {ip}", "lookup {ip}", "look up ip {ip}"],
    examples=["8.8.8.8", "ip 1.1.1.1"],
    inputs={"ip": Input(required=True, pattern=IP, ask="🌐 Which IP address? (e.g. *8.8.8.8*)")})
async def lookup(ctx, ip):
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        raise UserError("🌐 That doesn't look like an IP address, e.g. *8.8.8.8*.") from None
    if not addr.is_global:
        raise UserError("🔒 That's a private/reserved address — only public IPs can be looked up.")
    r = await ctx.services.http.get(f"https://ipinfo.io/{addr}/json")
    r.raise_for_status()
    d = r.json()
    return (f"🌐 *{d.get('ip')}*\n📍 {', '.join(x for x in (d.get('city'), d.get('region'), d.get('country')) if x)}\n"
            f"🏢 {d.get('org', '—')}\n🕐 {d.get('timezone', '—')}" + (f"\n🔖 {d['hostname']}" if d.get("hostname") else ""))
