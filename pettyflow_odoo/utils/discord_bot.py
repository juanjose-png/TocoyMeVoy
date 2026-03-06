import discord
from discord import app_commands
import json
import os
import sys
import logging
from datetime import datetime
from aiohttp import web
import asyncio

# Configuración de logging
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
log_dir = os.path.join(root_dir, '.agent', 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'discord_bot.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('AproBABot')

# Forzar codificación UTF-8 para evitar errores en Windows
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

logger.info("Iniciando AproBABot...")

# Configuración de intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# ID del servidor para sincronización instantánea
GUILD_ID = 1479455655235686512

# --- UI COMPONENTS (MODALS & VIEWS) ---

class VincularCuentaModal(discord.ui.Modal, title="Vincular Cuenta Solenium"):
    correo = discord.ui.TextInput(label="Correo o Nombre (TARJETA)", placeholder="Ej: Estefania Olarte", min_length=3, max_length=100)
    
    async def on_submit(self, interaction: discord.Interaction):
        bot.update_user_activity(interaction.user.id, interaction.channel_id)
        await vincular_cuenta_logic(interaction, self.correo.value)

class SolicitarRecargaModal(discord.ui.Modal, title="Solicitar Recarga"):
    monto = discord.ui.TextInput(label="Monto a solicitar", placeholder="Ej: 500000", min_length=1, max_length=10)
    
    async def on_submit(self, interaction: discord.Interaction):
        bot.update_user_activity(interaction.user.id, interaction.channel_id)
        try:
            monto_int = int(self.monto.value)
            await solicitar_recarga_logic(interaction, monto_int)
        except ValueError:
            await interaction.response.send_message("❌ Error: Ingresa un número válido para el monto.", ephemeral=True)

class ConfirmacionRecargaView(discord.ui.View):
    def __init__(self, solicitante_id, admin_id, monto, solicitante_nombre):
        super().__init__(timeout=None)
        self.solicitante_id = solicitante_id
        self.admin_id = admin_id
        self.monto = monto
        self.solicitante_nombre = solicitante_nombre

    @discord.ui.button(label="💳 Confirmar Recarga", style=discord.ButtonStyle.primary, custom_id="btn_confirmar_final")
    async def btn_confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot.update_user_activity(interaction.user.id, interaction.channel_id)
        # Permisos: Estefania Olarte (Admin) o Tesorería (tesoreria@solenium.co)
        admin_estefania = "1272556958330916936"
        autor_id = str(interaction.user.id)
        
        mapping = get_mapping()
        user_info = mapping.get(autor_id, {})
        user_email = user_info.get('correo', '').lower()
        
        # Validar si es Estefania o el correo de Tesorería
        if autor_id != admin_estefania and user_email != "tesoreria@solenium.co":
            await interaction.response.send_message("⛔ Solo el personal de **Tesorería** (tesoreria@solenium.co) o la Administradora pueden confirmar la recarga.", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        # Actualizar estado en solicitudes.json (Aprobado -> Recargado)
        update_request_status(self.solicitante_nombre, self.monto, "Recargado")

        confirm_msg = (
            f"📢 **RECARGA EXITOSA (REALIZADA)**\n"
            f"✅ <@{self.solicitante_id}>, tu recarga por **${self.monto:,}** ya ha sido procesada con éxito.\n"
            f"👤 Notificado a Administrador: <@{self.admin_id}>\n"
            f"💳 Realizado por: {interaction.user.mention} (Tesorería)"
        )
        await interaction.followup.send(confirm_msg)
        logger.info(f"Recarga confirmada por {interaction.user}: {self.solicitante_nombre} (${self.monto:,})")

class AprobarMontoModal(discord.ui.Modal, title="Confirmar Monto a Aprobar"):
    monto = discord.ui.TextInput(label="Monto Autorizado", placeholder="Ej: 500000", min_length=1, max_length=10)
    
    def __init__(self, view):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        bot.update_user_activity(interaction.user.id, interaction.channel_id)
        try:
            monto_final = int(self.monto.value)
            
            # Deshabilitar botones en la vista original
            for child in self.view.children:
                child.disabled = True
            
            # Responder al modal editando el mensaje original para deshabilitar botones
            await interaction.response.edit_message(view=self.view)
            
            # Registrar aprobación en el historial mensual con el monto final
            record_approval(self.view.solicitante_discord_id, monto_final)
            
            # Actualizar estado en solicitudes.json (Pendiente -> Aprobado)
            update_request_status(self.view.solicitante_nombre, self.view.monto, "Aprobado")
            
            confirm_msg = (
                f"🎊 **RECARGA APROBADA**\n"
                f"✅ Se ha aprobado la solicitud de **{self.view.solicitante_nombre}** (<@{self.view.solicitante_discord_id}>) por un valor de **${monto_final:,}**.\n"
                f"👤 Aprobado por: {interaction.user.mention}\n"
                f"⏳ Pendiente de confirmación por Tesorería."
            )
            
            # Enviar mensaje con el botón de confirmación para Tesorería
            view_confirmar = ConfirmacionRecargaView(
                solicitante_id=self.view.solicitante_discord_id,
                admin_id=str(interaction.user.id),
                monto=monto_final,
                solicitante_nombre=self.view.solicitante_nombre
            )
            
            await interaction.followup.send(confirm_msg, view=view_confirmar)
            logger.info(f"Recarga aprobada manualmente por {interaction.user}: {self.view.solicitante_nombre} (${monto_final:,})")
            
        except ValueError:
            await (interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send)("❌ Error: Ingresa un número válido.", ephemeral=True)

class SolicitudAprobacionView(discord.ui.View):
    def __init__(self, solicitante_nombre, monto, solicitante_discord_id):
        super().__init__(timeout=None)
        self.solicitante_nombre = solicitante_nombre
        self.monto = monto
        self.solicitante_discord_id = solicitante_discord_id

    @discord.ui.button(label="✅ Aprobar", style=discord.ButtonStyle.success, custom_id="btn_aprobar_directo")
    async def btn_aprobar(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot.update_user_activity(interaction.user.id, interaction.channel_id)
        # Seguridad: Solo Estefania Olarte (ID mapeado) puede aprobar
        estefania_id = "1272556958330916936"
        autor_id = str(interaction.user.id)
        
        if autor_id != estefania_id:
            await interaction.response.send_message("⛔ Solo Estefania Olarte puede aprobar solicitudes de recarga.", ephemeral=True)
            return

        # Abrir modal para consultar monto final
        await interaction.response.send_modal(AprobarMontoModal(self))

class AccionesBotView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📲 Vincular Cuenta", style=discord.ButtonStyle.primary, custom_id="btn_vincular")
    async def btn_vincular(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot.update_user_activity(interaction.user.id, interaction.channel_id)
        await interaction.response.send_modal(VincularCuentaModal())

    @discord.ui.button(label="💰 Solicitar Recarga", style=discord.ButtonStyle.success, custom_id="btn_solicitar")
    async def btn_solicitar(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot.update_user_activity(interaction.user.id, interaction.channel_id)
        mapping = get_mapping()
        user_info = mapping.get(str(interaction.user.id))
        
        if not user_info:
            await interaction.response.send_message("❌ Error: Tu cuenta no está vinculada. Usa **Vincular Cuenta** primero.", ephemeral=True)
            return
            
        # Si está vinculado, no pedimos monto y enviamos directo la solicitud
        await solicitar_recarga_logic(interaction, monto=None)

    @discord.ui.button(label="📢 Ver Saldo Disponible", style=discord.ButtonStyle.secondary, custom_id="btn_saldo")
    async def btn_saldo(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot.update_user_activity(interaction.user.id, interaction.channel_id)
        mapping = get_mapping()
        user_info = mapping.get(str(interaction.user.id))
        
        if not user_info:
            await interaction.response.send_message("❌ Error: Tu cuenta no está vinculada.", ephemeral=True)
            return
            
        presupuestos = get_presupuestos()
        perfil = next((p for p in presupuestos if p['tarjeta'] == user_info['tarjeta']), None)
        
        if not perfil:
            await interaction.response.send_message("❌ Error: No se encontró tu perfil.", ephemeral=True)
            return

        cupo_total = perfil.get('cupo_mensual', 0)
        if isinstance(cupo_total, str): 
            # Si es "Pendiente...", mostramos un mensaje específico
            await interaction.response.send_message(f"ℹ️ Hola **{perfil['tarjeta']}**, tu cupo mensual está sujeto a **aprobación manual previa de Alan M**. Consulta con él tu saldo disponible.", ephemeral=True)
            return
        
        # Calcular fechas de vigencia (mes actual)
        now = datetime.now()
        ultimo_dia = 31 if now.month in [1, 3, 5, 7, 8, 10, 12] else (30 if now.month != 2 else (29 if now.year % 4 == 0 else 28))
        periodo_uso = f"del **01/{now.month:02}/{now.year}** al **{ultimo_dia:02}/{now.month:02}/{now.year}**"
        
        gastado = get_history().get(str(interaction.user.id), 0)
        saldo_actual = max(0, cupo_total - gastado)
        
        if saldo_actual <= 0:
            msg = (
                f"¡Hola **{perfil['tarjeta']}**! 🧐 Revisé tus movimientos y...\n\n"
                f"💰 **Cupo Mensual:** ${cupo_total:,}\n"
                f"📉 **Recargas Realizadas:** ${gastado:,}\n"
                f"🔴 **Saldo Actual:** **$0**\n\n"
                f"📅 **Periodo de uso:** {periodo_uso}\n\n"
                "Has aprovechado al máximo tu cupo mensual. Recuerda que el primer día del próximo mes tu cupo "
                "se renueva automáticamente. ¡A contar los días!"
            )
        else:
            msg = (
                f"✅ Hola **{perfil['tarjeta']}**, aquí tienes el resumen de tu saldo:\n\n"
                f"💰 **Cupo Mensual:** ${cupo_total:,}\n"
                f"📉 **Recargas Realizadas:** ${gastado:,}\n"
                f"🟢 **Saldo Disponible:** **${saldo_actual:,}**\n\n"
                f"📅 **Válido para uso:** {periodo_uso}\n\n"
                "Recuerda solicitar tus recargas con anticipación."
            )
            
        await interaction.response.send_message(msg, ephemeral=True)

import asyncio
from discord.ext import tasks

# --- BOT INTERFACE & LOGIC ---

class AproBABot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        
        # Rutas de datos
        self.data_path = os.path.join(root_dir, '.agent', 'data', 'presupuestos_iniciales.json')
        self.mapping_path = os.path.join(root_dir, '.agent', 'data', 'discord_mapping.json')
        self.history_path = os.path.join(root_dir, '.agent', 'data', 'aprobaciones_mensuales.json')
        self.solicitudes_path = os.path.join(root_dir, '.agent', 'data', 'solicitudes.json')
        
        # Registro de actividad para timeouts (user_id -> {"time": datetime, "channel_id": int})
        self.user_activity = {}
        
        # Lista de Visitadores que requieren etiqueta a Alan M
        self.visitadores = [
            "Mauro Madera", "Milton Arcos", "Julio Cesar", 
            "Benjamin Juli Owen", "Bayron Cajica", "Derwin Urdaneta"
        ]

    async def setup_hook(self):
        os.makedirs(os.path.dirname(self.mapping_path), exist_ok=True)
        for path in [self.mapping_path, self.history_path, self.solicitudes_path]:
            if not os.path.exists(path):
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump([] if path == self.solicitudes_path else {}, f)
        
        # Iniciar servidor web interno para comunicación con el Dashboard
        self.loop.create_task(self.run_webserver())
        
        # Iniciar monitoreo de inactividad
        self.check_inactivity_task.start()
        
        # Sincronización instantánea para el servidor de pruebas
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        logger.info("Comandos sincronizados de forma instantánea para el gremio %s", GUILD_ID)

    def update_user_activity(self, user_id, channel_id):
        """ Actualiza la marca de tiempo de la última actividad del usuario. """
        self.user_activity[user_id] = {
            "time": datetime.now(),
            "channel_id": channel_id
        }

    @tasks.loop(minutes=1.0)
    async def check_inactivity_task(self):
        """ Revisa usuarios inactivos por más de 3 minutos. """
        now = datetime.now()
        inactivos = []
        
        for user_id, info in list(self.user_activity.items()):
            delta = (now - info['time']).total_seconds()
            if delta >= 180: # 3 minutos
                inactivos.append((user_id, info['channel_id']))
                
        for user_id, channel_id in inactivos:
            try:
                channel = self.get_channel(channel_id)
                if channel:
                    await channel.send(f"⚠️ <@{user_id}>, por inactividad se cierra la sesión.")
                del self.user_activity[user_id]
                logger.info(f"Sesión cerrada por inactividad: Usuario ID {user_id}")
            except Exception as e:
                logger.error(f"Error al notificar inactividad a {user_id}: {e}")

    @check_inactivity_task.before_loop
    async def before_check_inactivity(self):
        await self.wait_until_ready()

    async def run_webserver(self):
        app = web.Application()
        app.router.add_post('/aprobar', self.handle_approval_api)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, 'localhost', 5000)
        await site.start()
        logger.info("Servidor API interno escuchando en http://localhost:5000")

    async def handle_approval_api(self, request):
        data = await request.json()
        user_name = data.get('usuario')
        monto = data.get('monto')
        admin_email = data.get('admin_email')
        
        # Encontrar discord_id del solicitante
        mapping = get_mapping()
        discord_id = next((uid for uid, info in mapping.items() if info['tarjeta'] == user_name), None)
        
        if not discord_id:
            return web.json_response({"error": "Usuario no encontrado en mapping"}, status=404)

        # Canal privado (Tesorería/Dashboard Notification)
        # Por ahora enviamos al canal general o un canal fijo de notificaciones si existe
        channel = self.get_channel(1479455655235686512) # Canal actual, ajustar si hay uno de logs
        if not channel:
            # fallback al primer canal disponible
            channel = [c for c in self.get_all_channels() if isinstance(c, discord.TextChannel)][0]

        confirm_msg = (
            f"🎊 **APROBACIÓN DESDE DASHBOARD**\n"
            f"✅ Se ha aprobado la solicitud de **{user_name}** (<@{discord_id}>) por un valor de **${monto:,}**.\n"
            f"👤 Autorizado por: {admin_email} (Dashboard)\n"
            f"🚀 *Ironía: Alguien está trabajando duro en el Dashboard mientras el resto toma café.*"
        )
        
        await channel.send(confirm_msg)
        
        # Registrar y actualizar estados
        record_approval(discord_id, monto)
        update_request_status(user_name, monto, "Aprobado")
        
        return web.json_response({"status": "ok"})

    async def on_ready(self):
        logger.info(f'AproBABot online como {self.user} (ID: {self.user.id})')
        logger.info(f'Conectado en {len(self.guilds)} servidores:')
        for guild in self.guilds:
            logger.info(f' - {guild.name} (ID: {guild.id})')

    async def on_message(self, message):
        if message.author == self.user:
            return
        
        if message.content.lower() == '!ping':
            self.update_user_activity(message.author.id, message.channel.id)
            await message.channel.send('¡Pong! AproBABot está vivo y reportando.')
            logger.info(f"Ping recibido de {message.author}")

# Instancia global del bot
bot = AproBABot()

def get_mapping():
    if os.path.exists(bot.mapping_path):
        with open(bot.mapping_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def get_presupuestos():
    if os.path.exists(bot.data_path):
        with open(bot.data_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def get_history():
    if os.path.exists(bot.history_path):
        try:
            with open(bot.history_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Reset mensual simple (basado en mes actual en el archivo)
                current_month = datetime.now().strftime("%Y-%m")
                if data.get("current_month") != current_month:
                    return {"current_month": current_month}
                return data
        except: pass
    return {"current_month": datetime.now().strftime("%Y-%m")}

def record_approval(user_id, monto):
    history = get_history()
    user_id_str = str(user_id)
    history[user_id_str] = history.get(user_id_str, 0) + monto
    with open(bot.history_path, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=4)

def record_approval_by_name(tarjeta_name, monto):
    """ Permite registrar una recarga desde Odoo usando el nombre del empleado. """
    mapping = get_mapping()
    # Buscar Discord ID inverso
    discord_id = next((uid for uid, info in mapping.items() if info['tarjeta'] == tarjeta_name), None)
    if discord_id:
        record_approval(discord_id, monto)
        return True
    return False

def get_solicitudes():
    if os.path.exists(bot.solicitudes_path):
        with open(bot.solicitudes_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def record_request(user_name, email, monto, discord_id):
    solicitudes = get_solicitudes()
    nueva = {
        "id": len(solicitudes) + 1,
        "usuario": user_name,
        "correo": email,
        "monto": monto,
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "estado": "Pendiente",
        "discord_id": str(discord_id)
    }
    solicitudes.append(nueva)
    with open(bot.solicitudes_path, 'w', encoding='utf-8') as f:
        json.dump(solicitudes, f, indent=4)
    return nueva["id"]

def update_request_status(user_name, monto, nuevo_estado):
    solicitudes = get_solicitudes()
    for s in reversed(solicitudes):
        if s["usuario"] == user_name and s["monto"] == monto and s["estado"] != "Recargado":
            s["estado"] = nuevo_estado
            break
    with open(bot.solicitudes_path, 'w', encoding='utf-8') as f:
        json.dump(solicitudes, f, indent=4)

# --- REUSED LOGIC FUNCTIONS ---

async def vincular_cuenta_logic(interaction, correo):
    try:
        # Validación de dominio corporativo
        if not correo.lower().endswith("@solenium.co"):
            await (interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send)(
                "❌ Error: Debes usar tu correo corporativo de **@solenium.co** para vincular tu cuenta.", ephemeral=True
            )
            return

        presupuestos = get_presupuestos()
        # Buscar coincidencia: comprobamos si el correo ingresado coincide con el campo 'correo' 
        # o si el nombre (antes del @) coincide con el campo 'tarjeta' (por si acaso el JSON no tiene correos aún)
        email_user = correo.lower().split("@")[0]
        perfil = next((p for p in presupuestos if p.get('correo', '').lower() == correo.lower() or p['tarjeta'].lower() == email_user.replace(".", " ")), None)
        
        # fallback: si no hay correo en el JSON, buscamos por nombre exacto si el usuario escribió su nombre en lugar de correo (pero arriba forzamos @solenium.co)
        # Ajustamos para que pueda buscar por el nombre de la tarjeta en minúsculas
        if not perfil:
            perfil = next((p for p in presupuestos if p['tarjeta'].lower() in correo.lower()), None)

        if not perfil:
            await (interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send)(
                f"❌ No se encontró ningún perfil autorizado para **{correo}**. Por favor contacta a Estefania Olarte.", ephemeral=True
            )
            return

        mapping = get_mapping()
        mapping[str(interaction.user.id)] = {
            'tarjeta': perfil['tarjeta'], 
            'correo': correo.lower(), 
            'lider': perfil.get('lider', '')
        }
        with open(bot.mapping_path, 'w', encoding='utf-8') as f: 
            json.dump(mapping, f, indent=4)

        msg = f"✅ ¡Cuenta vinculada exitosamente! Perfil: **{perfil['tarjeta']}**."
        if perfil['tarjeta'] in bot.visitadores: 
            msg += "\n⚠️ Nota: Requiere aprobación de @Alan M."
        
        await (interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send)(msg, ephemeral=True)
        logger.info(f"Vínculo exitoso: {interaction.user} ({correo}) -> {perfil['tarjeta']}")
    except Exception as e:
        logger.error(f"Error vinculación: {e}")
        await (interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send)(
            "❌ Ocurrió un error al intentar vincular tu cuenta.", ephemeral=True
        )

async def solicitar_recarga_logic(interaction, monto):
    mapping = get_mapping()
    user_info = mapping.get(str(interaction.user.id))
    if not user_info:
        await interaction.response.send_message("❌ Vincula tu cuenta primero.", ephemeral=True)
        return
    
    presupuestos = get_presupuestos()
    perfil = next((p for p in presupuestos if p['tarjeta'] == user_info['tarjeta']), None)
    
    # Si no se provee monto (desde el botón), usamos el estándar del perfil
    if monto is None:
        monto = perfil.get('monto_por_recarga', 0)
        if isinstance(monto, str): monto = 0
    
    max_recarga = perfil.get('monto_por_recarga', 0)
    if isinstance(max_recarga, str): max_recarga = 0
    
    if monto > max_recarga and max_recarga > 0:
        await interaction.response.send_message(f"❌ Exceso de monto. Tu máximo es: **${max_recarga:,}**.", ephemeral=True)
        return
        
    dia_semana = datetime.now().weekday()
    msg_extra = "\n🚀 *Tu recarga está en proceso; estamos siendo más ágiles que el área de sistemas cuando se cae el internet.*" if dia_semana in [0, 1] else ""
    
    # ID de Estefania Olarte para mención
    estefania_id = "1272556958330916936"
    mencion_estefania = f"<@{estefania_id}>"
    
    view = SolicitudAprobacionView(solicitante_nombre=perfil['tarjeta'], monto=monto, solicitante_discord_id=str(interaction.user.id))
    
    # Lógica de Visitadores (Alan M)
    if perfil['tarjeta'] in bot.visitadores:
        await interaction.response.send_message(f"⏳ **{perfil['tarjeta']}** solicita aprobación de recarga. {mencion_estefania} favor validar (requiere aprobación adicional de **Alan M**).{msg_extra}", view=view, ephemeral=False)
        return
        
    await (interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send)(f"✅ **{perfil['tarjeta']}** solicita aprobación de recarga. {mencion_estefania} favor validar.{msg_extra}", view=view, ephemeral=False)
    
    # Registrar solicitud en solicitudes.json
    record_request(perfil['tarjeta'], user_info['correo'], monto, str(interaction.user.id))
    
    logger.info(f"Solicitud enviada por {perfil['tarjeta']} (Monto: {monto})")

# --- SLASH COMMANDS ---

@bot.tree.command(name="acciones", description="Muestra el menú de acciones rápidas")
async def acciones(interaction: discord.Interaction):
    bot.update_user_activity(interaction.user.id, interaction.channel_id)
    embed = discord.Embed(title="🤖 Menú de Acciones AproBABot", description="Usa los botones para gestionar tus recargas rápidamente.", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, view=AccionesBotView())

@bot.tree.command(name="vincular_cuenta", description="Vincula tu cuenta Solenium")
async def self_vincular_cuenta(interaction: discord.Interaction, correo: str):
    bot.update_user_activity(interaction.user.id, interaction.channel_id)
    await vincular_cuenta_logic(interaction, correo)

@bot.tree.command(name="solicitar_recarga", description="Solicita una recarga")
async def self_solicitar_recarga(interaction: discord.Interaction, monto: int):
    bot.update_user_activity(interaction.user.id, interaction.channel_id)
    await solicitar_recarga_logic(interaction, monto)

@bot.tree.command(name="confirmar_recarga", description="Confirmar recarga (Tesorería)")
async def confirmar_recarga(interaction: discord.Interaction, usuario: discord.Member, monto: int):
    bot.update_user_activity(interaction.user.id, interaction.channel_id)
    # (Mantengo la lógica existente)
    autor_info = get_mapping().get(str(interaction.user.id))
    if not (autor_info and (autor_info['tarjeta'] == "Administrador" or autor_info['lider'] == "Administrador")):
        await interaction.response.send_message("⛔ Sin permisos.", ephemeral=True)
        return
    canales = [g.system_channel for g in bot.guilds if g.system_channel]
    target = canales[0] if canales else interaction.channel
    await target.send(f"📢 **RECARGA EXITOSA**\n✅ Confirmado para {usuario.mention} por **${monto:,}**.")
    await interaction.response.send_message("✅ Confirmado.", ephemeral=True)

async def enviar_notificacion_grupal(canal_id, mensaje):
    channel = bot.get_channel(int(canal_id))
    if channel: await channel.send(mensaje)

if __name__ == "__main__":
    TOKEN = "MTQ3OTQ0OTczNDkyMTA2MDM5Mg.G69c0r.re55YmhqkSoJ4YOqEE2NIPZsARo5Y9cULFQ6Lc"
    try: bot.run(TOKEN)
    except Exception as e: logger.critical(f"FATAL: {e}")
