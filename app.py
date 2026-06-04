import os
import random
import string
from flask import Flask, render_template, request, jsonify, redirect, url_for, Response, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import json
import csv
from io import StringIO

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__, template_folder=os.path.join(basedir, 'templates'))
app.config['SECRET_KEY'] = 'clave_super_secreta_2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'posada.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static', 'uploads')

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_admin'

# ============================================================
# MODELOS
# ============================================================

class Posada(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), default='Mi Posada')
    direccion = db.Column(db.String(200))
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(100))
    logo = db.Column(db.String(200))
    color_primario = db.Column(db.String(7), default='#2C5F8A')
    color_secundario = db.Column(db.String(7), default='#51CF66')
    activo = db.Column(db.Boolean, default=True)

class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(500), nullable=False)
    rol = db.Column(db.String(20), default='admin')
    posada_id = db.Column(db.Integer, db.ForeignKey('posada.id'))

class Habitacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100))
    tipo = db.Column(db.String(50))
    capacidad = db.Column(db.Integer)
    camas = db.Column(db.String(100))
    precio_base = db.Column(db.Float)
    descripcion = db.Column(db.Text)
    servicios = db.Column(db.Text, default='["wifi","ac","tv"]')
    estado = db.Column(db.String(20), default='disponible')
    imagen = db.Column(db.String(200))
    posada_id = db.Column(db.Integer, db.ForeignKey('posada.id'))

class Reserva(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    localizador = db.Column(db.String(20), unique=True, nullable=True)
    cliente_nombre = db.Column(db.String(100))
    cliente_cedula = db.Column(db.String(20))
    cliente_telefono = db.Column(db.String(20))
    cliente_email = db.Column(db.String(100))
    fecha_entrada = db.Column(db.Date)
    fecha_salida = db.Column(db.Date)
    adultos = db.Column(db.Integer, default=1)
    ninos = db.Column(db.Integer, default=0)
    total = db.Column(db.Float)
    estado = db.Column(db.String(20), default='pendiente')
    metodo_pago = db.Column(db.String(50))
    comprobante = db.Column(db.String(200))
    datos_huespedes = db.Column(db.Text)
    habitacion_id = db.Column(db.Integer, db.ForeignKey('habitacion.id'))
    posada_id = db.Column(db.Integer, db.ForeignKey('posada.id'))
    fecha_reserva = db.Column(db.DateTime, default=datetime.utcnow)
    aprobado_por = db.Column(db.String(100))
    fecha_aprobacion = db.Column(db.DateTime)
    comentario_rechazo = db.Column(db.Text)
    solo_reserva = db.Column(db.Boolean, default=False)
    fecha_expiracion = db.Column(db.DateTime)

class Tarifa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100))
    tipo = db.Column(db.String(50))
    multiplicador = db.Column(db.Float, default=0)
    fecha_inicio = db.Column(db.Date, nullable=True)
    fecha_fin = db.Column(db.Date, nullable=True)
    dias_aplicacion = db.Column(db.String(50), nullable=True)
    posada_id = db.Column(db.Integer, db.ForeignKey('posada.id'))

class Agencia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100))
    email = db.Column(db.String(100))
    password_hash = db.Column(db.String(500))
    activo = db.Column(db.Boolean, default=True)
    posada_id = db.Column(db.Integer, db.ForeignKey('posada.id'))

class Configuracion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(50))
    valor = db.Column(db.String(100))
    posada_id = db.Column(db.Integer, db.ForeignKey('posada.id'))

class LogActividad(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    accion = db.Column(db.String(50))
    descripcion = db.Column(db.Text)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    posada_id = db.Column(db.Integer, db.ForeignKey('posada.id'))

# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def generar_localizador(posada_id):
    """Genera un localizador único tipo POS-ABC123 reutilizable cada 3 meses"""
    while True:
        letras = ''.join(random.choices(string.ascii_uppercase, k=3))
        numeros = ''.join(random.choices(string.digits, k=3))
        localizador = f"POS-{letras}{numeros}"
        
        # Verificar que no existe en los últimos 3 meses
        hace_3_meses = datetime.utcnow() - timedelta(days=90)
        existe = Reserva.query.filter(
            Reserva.localizador == localizador,
            Reserva.fecha_reserva > hace_3_meses
        ).first()
        
        if not existe:
            return localizador

def registrar_log(usuario_id, accion, descripcion, posada_id=None):
    """Registra una acción en los logs del sistema"""
    try:
        log = LogActividad(
            usuario_id=usuario_id,
            accion=accion,
            descripcion=descripcion,
            posada_id=posada_id or 1
        )
        db.session.add(log)
        db.session.commit()
    except:
        pass

def cancelar_reservas_expiradas():
    ahora = datetime.utcnow()
    reservas_expiradas = Reserva.query.filter(
        Reserva.solo_reserva == True,
        Reserva.estado == 'pendiente',
        Reserva.fecha_expiracion != None,
        Reserva.fecha_expiracion < ahora
    ).all()
    for r in reservas_expiradas:
        r.estado = 'cancelada'
        r.comentario_rechazo = 'Cancelada automáticamente por tiempo límite'
    if reservas_expiradas:
        db.session.commit()

def calcular_tarifa_aplicable(posada_id, fecha):
    ajuste = 0
    tarifas = Tarifa.query.filter_by(posada_id=posada_id).all()
    for t in tarifas:
        if t.tipo == 'rango_fechas' and t.fecha_inicio and t.fecha_fin:
            if t.fecha_inicio <= fecha <= t.fecha_fin:
                ajuste += t.multiplicador
        elif t.tipo in ['dias_semana', 'dias_especificos'] and t.dias_aplicacion:
            dia_semana = fecha.weekday()
            dias = [int(d) for d in t.dias_aplicacion.split(',')]
            if dia_semana in dias:
                ajuste += t.multiplicador
    return ajuste

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Usuario, int(user_id))

# ============================================================
# RUTAS BÁSICAS
# ============================================================

@app.route('/')
def inicio():
    return render_template('cliente/inicio.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def login_admin():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = Usuario.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            registrar_log(user.id, 'login', f'Inicio de sesión de {user.username}')
            return redirect(url_for('panel_admin'))
    return render_template('admin/login.html')

@app.route('/admin')
@login_required
def panel_admin():
    return render_template('admin/dashboard.html')

@app.route('/admin/logout')
@login_required
def logout_admin():
    registrar_log(current_user.id, 'logout', f'Cierre de sesión de {current_user.username}')
    logout_user()
    return redirect(url_for('login_admin'))

# ============================================================
# API HABITACIONES
# ============================================================

@app.route('/api/habitaciones', methods=['GET'])
@login_required
def obtener_habitaciones():
    cancelar_reservas_expiradas()
    habitaciones = Habitacion.query.filter_by(posada_id=current_user.posada_id).all()
    return jsonify([{
        'id': h.id, 'nombre': h.nombre, 'tipo': h.tipo,
        'capacidad': h.capacidad, 'precio_base': h.precio_base,
        'descripcion': h.descripcion, 'estado': h.estado,
        'imagen': h.imagen, 'camas': h.camas,
        'servicios': json.loads(h.servicios) if h.servicios else []
    } for h in habitaciones])

@app.route('/api/habitaciones', methods=['POST'])
@login_required
def crear_habitacion():
    try:
        nombre = request.form.get('nombre')
        tipo = request.form.get('tipo')
        capacidad = int(request.form.get('capacidad'))
        precio_base = float(request.form.get('precio_base'))
        descripcion = request.form.get('descripcion', '')
        camas = request.form.get('camas', '')
        servicios = request.form.get('servicios', '["wifi","ac","tv"]')
        
        imagen = None
        if 'imagen' in request.files:
            file = request.files['imagen']
            if file.filename:
                filename = secure_filename(file.filename)
                filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                imagen = filename
        
        hab = Habitacion(
            nombre=nombre, tipo=tipo, capacidad=capacidad, camas=camas,
            precio_base=precio_base, descripcion=descripcion, servicios=servicios,
            imagen=imagen, posada_id=current_user.posada_id
        )
        db.session.add(hab)
        db.session.commit()
        
        registrar_log(current_user.id, 'crear_habitacion', f'Creó habitación: {nombre}')
        
        return jsonify({'message': 'Habitacion creada', 'id': hab.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/habitaciones/<int:id>', methods=['PUT'])
@login_required
def actualizar_habitacion(id):
    hab = db.session.get(Habitacion, id)
    if not hab or hab.posada_id != current_user.posada_id:
        return jsonify({'error': 'No encontrada'}), 404
    
    try:
        if request.is_json:
            data = request.get_json()
            for campo in ['nombre', 'tipo', 'capacidad', 'camas', 'precio_base', 'descripcion', 'servicios']:
                if campo in data:
                    setattr(hab, campo, data[campo])
        else:
            for campo in ['nombre', 'tipo', 'capacidad', 'camas', 'precio_base', 'descripcion', 'servicios']:
                if campo in request.form:
                    setattr(hab, campo, request.form[campo])
            if 'imagen' in request.files:
                file = request.files['imagen']
                if file and file.filename:
                    if hab.imagen:
                        old_path = os.path.join(app.config['UPLOAD_FOLDER'], hab.imagen)
                        if os.path.exists(old_path): os.remove(old_path)
                    filename = secure_filename(file.filename)
                    filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    hab.imagen = filename
        
        db.session.commit()
        registrar_log(current_user.id, 'editar_habitacion', f'Editó habitación: {hab.nombre}')
        
        return jsonify({'message': 'Actualizada correctamente'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/habitaciones/<int:id>', methods=['DELETE'])
@login_required
def eliminar_habitacion(id):
    hab = db.session.get(Habitacion, id)
    if hab and hab.posada_id == current_user.posada_id:
        nombre = hab.nombre
        db.session.delete(hab)
        db.session.commit()
        registrar_log(current_user.id, 'eliminar_habitacion', f'Eliminó habitación: {nombre}')
        return jsonify({'message': 'Eliminada'})
    return jsonify({'error': 'No encontrada'}), 404

# ============================================================
# API DISPONIBILIDAD Y RESERVAS
# ============================================================

@app.route('/api/disponibilidad/<int:posada_id>')
def verificar_disponibilidad(posada_id):
    try:
        cancelar_reservas_expiradas()
        
        entrada_str = request.args.get('entrada')
        salida_str = request.args.get('salida')
        if not entrada_str or not salida_str:
            return jsonify([])
        
        entrada = datetime.strptime(entrada_str, '%Y-%m-%d').date()
        salida = datetime.strptime(salida_str, '%Y-%m-%d').date()
        
        todas_habitaciones = Habitacion.query.filter_by(posada_id=posada_id, estado='disponible').all()
        
        reservas_activas = Reserva.query.filter(
            Reserva.posada_id == posada_id,
            Reserva.habitacion_id.isnot(None),
            Reserva.estado != 'cancelada',
            Reserva.fecha_entrada <= salida,
            Reserva.fecha_salida >= entrada
        ).all()
        
        ocupadas_ids = list(set([r.habitacion_id for r in reservas_activas]))
        disponibles = [h for h in todas_habitaciones if h.id not in ocupadas_ids]
        
        dias = max((salida - entrada).days, 1)
        resultado = []
        for h in disponibles:
            total = h.precio_base * dias
            fecha = entrada
            while fecha < salida:
                ajuste = calcular_tarifa_aplicable(posada_id, fecha)
                total += ajuste
                fecha += timedelta(days=1)
            resultado.append({
                'id': h.id, 'nombre': h.nombre, 'tipo': h.tipo,
                'capacidad': h.capacidad, 'precio_total': round(total, 2),
                'precio_por_noche': round(total/dias, 2), 'descripcion': h.descripcion or '',
                'servicios': json.loads(h.servicios) if h.servicios else [],
                'imagen': h.imagen or '', 'camas': h.camas or ''
            })
        return jsonify(resultado)
    except Exception as e:
        print(f"Error: {e}")
        return jsonify([])

@app.route('/api/reservas', methods=['POST'])
def crear_reserva():
    try:
        datos = request.form
        entrada = datetime.strptime(datos.get('fecha_entrada'), '%Y-%m-%d').date()
        salida = datetime.strptime(datos.get('fecha_salida'), '%Y-%m-%d').date()
        dias = max((salida - entrada).days, 1)
        hab = db.session.get(Habitacion, int(datos.get('habitacion_id', 0)))
        
        if not hab:
            return jsonify({'error': 'Habitacion no encontrada'}), 404
        
        conflicto = Reserva.query.filter(
            Reserva.habitacion_id == hab.id,
            Reserva.estado != 'cancelada',
            Reserva.fecha_entrada <= salida,
            Reserva.fecha_salida >= entrada
        ).first()
        if conflicto:
            return jsonify({'error': 'Ya no está disponible'}), 409
        
        total = hab.precio_base * dias
        fecha = entrada
        while fecha < salida:
            ajuste = calcular_tarifa_aplicable(hab.posada_id, fecha)
            total += ajuste
            fecha += timedelta(days=1)
        
        metodo_pago = datos.get('metodo_pago', '')
        comprobante = None
        if metodo_pago not in ['efectivo', 'solo_reserva'] and 'comprobante' in request.files:
            file = request.files['comprobante']
            if file and file.filename:
                filename = secure_filename(file.filename)
                filename = f"pago_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                comprobante = filename
        
        solo_reserva = metodo_pago == 'solo_reserva'
        expiracion = datetime.utcnow() + timedelta(minutes=40) if solo_reserva else None
        
        # Generar localizador único
        localizador = generar_localizador(hab.posada_id)
        
        reserva = Reserva(
            localizador=localizador,
            cliente_nombre=datos.get('cliente_nombre', ''),
            cliente_cedula=datos.get('cliente_cedula', ''),
            cliente_telefono=datos.get('cliente_telefono', ''),
            cliente_email=datos.get('cliente_email', ''),
            fecha_entrada=entrada, fecha_salida=salida,
            adultos=int(datos.get('adultos', 1)),
            ninos=int(datos.get('ninos', 0)),
            total=round(total, 2),
            habitacion_id=hab.id, posada_id=hab.posada_id,
            metodo_pago=metodo_pago,
            comprobante=comprobante,
            datos_huespedes=datos.get('datos_huespedes', '[]'),
            estado='pendiente' if solo_reserva else 'pago_reportado',
            solo_reserva=solo_reserva,
            fecha_expiracion=expiracion
        )
        db.session.add(reserva)
        db.session.commit()
        
        registrar_log(1, 'nueva_reserva', f'Nueva reserva: {localizador} - {hab.nombre}')
        
        return jsonify({
            'message': 'Reserva creada exitosamente',
            'reserva_id': reserva.id,
            'localizador': reserva.localizador,
            'total': round(total, 2)
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/reservas/<int:reserva_id>', methods=['PUT'])
@login_required
def editar_reserva(reserva_id):
    """Solo admin puede editar reservas"""
    if current_user.rol != 'admin':
        return jsonify({'error': 'No autorizado. Solo administradores.'}), 403
    
    reserva = db.session.get(Reserva, reserva_id)
    if not reserva or reserva.posada_id != current_user.posada_id:
        return jsonify({'error': 'Reserva no encontrada'}), 404
    
    try:
        data = request.json
        if 'cliente_nombre' in data:
            reserva.cliente_nombre = data['cliente_nombre']
        if 'cliente_telefono' in data:
            reserva.cliente_telefono = data['cliente_telefono']
        if 'cliente_email' in data:
            reserva.cliente_email = data['cliente_email']
        if 'fecha_entrada' in data:
            reserva.fecha_entrada = datetime.strptime(data['fecha_entrada'], '%Y-%m-%d').date()
        if 'fecha_salida' in data:
            reserva.fecha_salida = datetime.strptime(data['fecha_salida'], '%Y-%m-%d').date()
        if 'estado' in data:
            reserva.estado = data['estado']
        if 'total' in data:
            reserva.total = float(data['total'])
        
        db.session.commit()
        registrar_log(current_user.id, 'editar_reserva', f'Editó reserva {reserva.localizador}')
        
        return jsonify({'message': 'Reserva actualizada correctamente'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ============================================================
# API TARIFAS
# ============================================================

@app.route('/api/tarifas', methods=['GET'])
@login_required
def obtener_tarifas():
    tarifas = Tarifa.query.filter_by(posada_id=current_user.posada_id).all()
    return jsonify([{
        'id': t.id, 'nombre': t.nombre, 'tipo': t.tipo,
        'multiplicador': t.multiplicador,
        'fecha_inicio': str(t.fecha_inicio) if t.fecha_inicio else None,
        'fecha_fin': str(t.fecha_fin) if t.fecha_fin else None,
        'dias_aplicacion': t.dias_aplicacion
    } for t in tarifas])

@app.route('/api/tarifas', methods=['POST'])
@login_required
def crear_tarifa():
    try:
        data = request.json
        tarifa = Tarifa(
            nombre=data['nombre'],
            tipo=data.get('tipo', 'rango_fechas'),
            multiplicador=float(data.get('multiplicador', 0)),
            fecha_inicio=datetime.strptime(data['fecha_inicio'], '%Y-%m-%d').date() if data.get('fecha_inicio') else None,
            fecha_fin=datetime.strptime(data['fecha_fin'], '%Y-%m-%d').date() if data.get('fecha_fin') else None,
            dias_aplicacion=data.get('dias_aplicacion'),
            posada_id=current_user.posada_id
        )
        db.session.add(tarifa)
        db.session.commit()
        registrar_log(current_user.id, 'crear_tarifa', f'Creó tarifa: {data["nombre"]}')
        return jsonify({'message': 'Tarifa creada'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/tarifas/<int:id>', methods=['DELETE'])
@login_required
def eliminar_tarifa(id):
    tarifa = db.session.get(Tarifa, id)
    if tarifa and tarifa.posada_id == current_user.posada_id:
        nombre = tarifa.nombre
        db.session.delete(tarifa)
        db.session.commit()
        registrar_log(current_user.id, 'eliminar_tarifa', f'Eliminó tarifa: {nombre}')
        return jsonify({'message': 'Tarifa eliminada'})
    return jsonify({'error': 'No encontrada'}), 404

# ============================================================
# API CALENDARIO Y RESERVAS (ADMIN)
# ============================================================

@app.route('/api/calendario-completo')
@login_required
def calendario_completo():
    cancelar_reservas_expiradas()
    mes = int(request.args.get('mes', datetime.now().month))
    año = int(request.args.get('año', datetime.now().year))
    inicio = datetime(año, mes, 1).date()
    fin = (datetime(año + 1, 1, 1) if mes == 12 else datetime(año, mes + 1, 1)).date() - timedelta(days=1)
    
    total_habitaciones = Habitacion.query.filter_by(posada_id=current_user.posada_id).count()
    
    reservas = Reserva.query.filter(
        Reserva.posada_id == current_user.posada_id,
        Reserva.estado != 'cancelada',
        Reserva.fecha_entrada <= fin,
        Reserva.fecha_salida >= inicio
    ).all()
    
    ocupacion_por_dia = {}
    for dia in range(1, fin.day + 1):
        fecha = datetime(año, mes, dia).date()
        ocupadas = sum(1 for r in reservas if r.fecha_entrada <= fecha <= r.fecha_salida)
        ocupacion_por_dia[fecha.strftime('%Y-%m-%d')] = {
            'ocupadas': ocupadas,
            'disponibles': total_habitaciones - ocupadas,
            'total': total_habitaciones
        }
    
    return jsonify({
        'total_dias': fin.day,
        'primer_dia_semana': (inicio.weekday() + 1) % 7,
        'mes': mes, 'año': año,
        'total_habitaciones': total_habitaciones,
        'ocupacion_por_dia': ocupacion_por_dia,
        'habitaciones': [{'id': h.id, 'nombre': h.nombre, 'tipo': h.tipo} 
                        for h in Habitacion.query.filter_by(posada_id=current_user.posada_id).all()]
    })

@app.route('/api/reservas-pendientes')
@login_required
def reservas_pendientes():
    cancelar_reservas_expiradas()
    reservas = Reserva.query.filter_by(posada_id=current_user.posada_id).filter(
        Reserva.estado.in_(['pago_reportado', 'pendiente'])
    ).order_by(Reserva.fecha_reserva.desc()).all()
    
    resultado = []
    for r in reservas:
        hab = db.session.get(Habitacion, r.habitacion_id)
        
        expiracion = None
        if r.fecha_expiracion:
            expiracion = (r.fecha_expiracion - timedelta(hours=4)).strftime('%d/%m/%Y %H:%M')
        
        fecha_aprob = None
        if r.fecha_aprobacion:
            fecha_aprob = (r.fecha_aprobacion - timedelta(hours=4)).strftime('%d/%m/%Y %H:%M')
        
        resultado.append({
            'id': r.id,
            'localizador': r.localizador,
            'cliente_nombre': r.cliente_nombre,
            'cliente_telefono': r.cliente_telefono or 'No registrado',
            'cliente_email': r.cliente_email or 'No registrado',
            'habitacion_nombre': hab.nombre if hab else 'N/A',
            'fecha_entrada': str(r.fecha_entrada),
            'fecha_salida': str(r.fecha_salida),
            'total': r.total,
            'estado': r.estado,
            'metodo_pago': r.metodo_pago or '-',
            'comprobante': r.comprobante,
            'datos_huespedes': r.datos_huespedes,
            'solo_reserva': r.solo_reserva,
            'fecha_expiracion': expiracion,
            'aprobado_por': r.aprobado_por,
            'fecha_aprobacion': fecha_aprob,
            'comentario_rechazo': r.comentario_rechazo,
            'fecha_reserva': (r.fecha_reserva - timedelta(hours=4)).strftime('%d/%m/%Y %H:%M')
        })
    return jsonify(resultado)

@app.route('/api/todas-reservas')
@login_required
def todas_reservas():
    cancelar_reservas_expiradas()
    reservas = Reserva.query.filter_by(posada_id=current_user.posada_id).order_by(Reserva.fecha_reserva.desc()).all()
    resultado = []
    for r in reservas:
        hab = db.session.get(Habitacion, r.habitacion_id)
        
        expiracion = None
        if r.fecha_expiracion:
            expiracion = (r.fecha_expiracion - timedelta(hours=4)).strftime('%d/%m/%Y %H:%M')
        
        fecha_aprob = None
        if r.fecha_aprobacion:
            fecha_aprob = (r.fecha_aprobacion - timedelta(hours=4)).strftime('%d/%m/%Y %H:%M')
        
        resultado.append({
            'id': r.id,
            'localizador': r.localizador,
            'cliente_nombre': r.cliente_nombre,
            'cliente_telefono': r.cliente_telefono or 'No registrado',
            'cliente_email': r.cliente_email or 'No registrado',
            'habitacion_nombre': hab.nombre if hab else 'N/A',
            'fecha_entrada': str(r.fecha_entrada),
            'fecha_salida': str(r.fecha_salida),
            'total': r.total,
            'estado': r.estado,
            'metodo_pago': r.metodo_pago or '-',
            'solo_reserva': r.solo_reserva,
            'fecha_expiracion': expiracion,
            'aprobado_por': r.aprobado_por,
            'fecha_aprobacion': fecha_aprob,
            'comentario_rechazo': r.comentario_rechazo,
            'fecha_reserva': (r.fecha_reserva - timedelta(hours=4)).strftime('%d/%m/%Y %H:%M')
        })
    return jsonify(resultado)

@app.route('/api/ingresos-mes')
@login_required
def ingresos_mes():
    mes = int(request.args.get('mes', datetime.now().month))
    año = int(request.args.get('año', datetime.now().year))
    inicio_mes = datetime(año, mes, 1).date()
    fin_mes = (datetime(año + 1, 1, 1) if mes == 12 else datetime(año, mes + 1, 1)).date() - timedelta(days=1)
    
    reservas = Reserva.query.filter(
        Reserva.posada_id == current_user.posada_id,
        Reserva.estado == 'confirmada',
        Reserva.fecha_entrada >= inicio_mes,
        Reserva.fecha_entrada <= fin_mes
    ).all()
    return jsonify({'total': round(sum(r.total for r in reservas), 2), 'cantidad': len(reservas)})

@app.route('/api/indicadores-dashboard')
@login_required
def indicadores_dashboard():
    """Indicadores avanzados para el dashboard"""
    try:
        posada_id = current_user.posada_id
        ahora = datetime.utcnow()
        hace_90_dias = ahora - timedelta(days=90)
        
        # Habitación más y menos vendida
        reservas_90d = Reserva.query.filter(
            Reserva.posada_id == posada_id,
            Reserva.estado == 'confirmada',
            Reserva.fecha_reserva >= hace_90_dias
        ).all()
        
        ventas_por_hab = {}
        for r in reservas_90d:
            hab = db.session.get(Habitacion, r.habitacion_id)
            nombre = hab.nombre if hab else 'Desconocida'
            if nombre not in ventas_por_hab:
                ventas_por_hab[nombre] = {'cantidad': 0, 'ingresos': 0}
            ventas_por_hab[nombre]['cantidad'] += 1
            ventas_por_hab[nombre]['ingresos'] += r.total
        
        mas_vendida = max(ventas_por_hab.items(), key=lambda x: x[1]['cantidad']) if ventas_por_hab else None
        menos_vendida = min(ventas_por_hab.items(), key=lambda x: x[1]['cantidad']) if ventas_por_hab else None
        
        # Mejor temporada
        ocupacion_por_mes = {}
        nombres_meses = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']
        for r in reservas_90d:
            mes = r.fecha_entrada.month
            if mes not in ocupacion_por_mes:
                ocupacion_por_mes[mes] = 0
            ocupacion_por_mes[mes] += 1
        
        mejor_mes = max(ocupacion_por_mes.items(), key=lambda x: x[1]) if ocupacion_por_mes else None
        
        # Ocupación actual
        hoy = ahora.date()
        ocupadas_hoy = Reserva.query.filter(
            Reserva.posada_id == posada_id,
            Reserva.estado != 'cancelada',
            Reserva.fecha_entrada <= hoy,
            Reserva.fecha_salida >= hoy
        ).count()
        
        total_habitaciones = Habitacion.query.filter_by(posada_id=posada_id).count()
        
        return jsonify({
            'mas_vendida': {
                'nombre': mas_vendida[0],
                'reservas': mas_vendida[1]['cantidad'],
                'ingresos': round(mas_vendida[1]['ingresos'], 2)
            } if mas_vendida else None,
            'menos_vendida': {
                'nombre': menos_vendida[0],
                'reservas': menos_vendida[1]['cantidad'],
                'ingresos': round(menos_vendida[1]['ingresos'], 2)
            } if menos_vendida else None,
            'mejor_temporada': {
                'mes': nombres_meses[mejor_mes[0]-1],
                'reservas': mejor_mes[1]
            } if mejor_mes else None,
            'ocupacion_hoy': {
                'ocupadas': ocupadas_hoy,
                'total': total_habitaciones,
                'porcentaje': round((ocupadas_hoy / total_habitaciones * 100) if total_habitaciones > 0 else 0, 1)
            },
            'total_reservas_90d': len(reservas_90d)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/logs')
@login_required
def ver_logs():
    """Ver logs de actividad (solo admin)"""
    if current_user.rol != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    
    logs = LogActividad.query.order_by(LogActividad.fecha.desc()).limit(100).all()
    return jsonify([{
        'id': log.id,
        'usuario': db.session.get(Usuario, log.usuario_id).username if log.usuario_id else 'Sistema',
        'accion': log.accion,
        'descripcion': log.descripcion,
        'fecha': (log.fecha - timedelta(hours=4)).strftime('%d/%m/%Y %H:%M:%S')
    } for log in logs])

@app.route('/api/validar-pago/<int:reserva_id>', methods=['POST'])
@login_required
def validar_pago(reserva_id):
    data = request.json
    reserva = db.session.get(Reserva, reserva_id)
    if reserva and reserva.posada_id == current_user.posada_id:
        accion = data.get('accion', 'confirmada')
        reserva.estado = accion
        reserva.aprobado_por = current_user.username
        reserva.fecha_aprobacion = datetime.utcnow()
        if reserva.estado == 'cancelada':
            reserva.comentario_rechazo = data.get('comentario', '')
        db.session.commit()
        registrar_log(current_user.id, 'validar_pago', f'{accion} reserva {reserva.localizador}')
        return jsonify({'message': 'Actualizado'})
    return jsonify({'error': 'No encontrada'}), 404

@app.route('/api/configuracion', methods=['GET'])
@login_required
def obtener_configuracion():
    configs = Configuracion.query.filter_by(posada_id=current_user.posada_id).all()
    posada = db.session.get(Posada, current_user.posada_id)
    return jsonify({
        'configuracion': {c.clave: c.valor for c in configs},
        'posada': {
            'nombre': posada.nombre,
            'direccion': posada.direccion,
            'telefono': posada.telefono,
            'email': posada.email,
            'color_primario': posada.color_primario,
            'color_secundario': posada.color_secundario
        } if posada else None
    })

@app.route('/api/configuracion', methods=['POST'])
@login_required
def guardar_configuracion():
    data = request.json
    # Guardar configuraciones
    if 'configuracion' in data:
        for clave, valor in data['configuracion'].items():
            config = Configuracion.query.filter_by(posada_id=current_user.posada_id, clave=clave).first()
            if config:
                config.valor = str(valor)
            else:
                db.session.add(Configuracion(clave=clave, valor=str(valor), posada_id=current_user.posada_id))
    
    # Guardar datos de la posada (personalización)
    if 'posada' in data:
        posada = db.session.get(Posada, current_user.posada_id)
        if posada:
            for campo in ['nombre', 'direccion', 'telefono', 'email', 'color_primario', 'color_secundario']:
                if campo in data['posada']:
                    setattr(posada, campo, data['posada'][campo])
    
    db.session.commit()
    registrar_log(current_user.id, 'guardar_configuracion', 'Actualizó configuración del sistema')
    return jsonify({'message': 'Guardado'})

# ============================================================
# PORTAL AGENCIAS
# ============================================================

@app.route('/agencia/login', methods=['GET', 'POST'])
def login_agencia():
    if request.method == 'POST':
        agencia = Agencia.query.filter_by(email=request.form.get('email'), activo=True).first()
        if agencia and check_password_hash(agencia.password_hash, request.form.get('password')):
            session['agencia_id'] = agencia.id
            session['agencia_nombre'] = agencia.nombre
            return redirect(url_for('panel_agencia'))
    return render_template('agencia/login.html')

@app.route('/agencia')
def panel_agencia():
    if not session.get('agencia_id'):
        return redirect(url_for('login_agencia'))
    return render_template('agencia/calendario.html')

@app.route('/agencia/logout')
def logout_agencia():
    session.pop('agencia_id', None)
    session.pop('agencia_nombre', None)
    return redirect(url_for('login_agencia'))

@app.route('/api/calendario-agencia')
def calendario_agencia():
    if not session.get('agencia_id'):
        return jsonify({'error': 'No autorizado'}), 403
    
    cancelar_reservas_expiradas()
    mes = int(request.args.get('mes', datetime.now().month))
    año = int(request.args.get('año', datetime.now().year))
    inicio = datetime(año, mes, 1).date()
    fin = (datetime(año + 1, 1, 1) if mes == 12 else datetime(año, mes + 1, 1)).date() - timedelta(days=1)
    
    todas_habitaciones = Habitacion.query.filter_by(posada_id=1).all()
    total_habitaciones = len(todas_habitaciones)
    
    reservas = Reserva.query.filter(
        Reserva.posada_id == 1,
        Reserva.estado != 'cancelada',
        Reserva.fecha_entrada <= fin,
        Reserva.fecha_salida >= inicio
    ).all()
    
    ocupacion_por_dia = {}
    for dia in range(1, fin.day + 1):
        fecha = datetime(año, mes, dia).date()
        fecha_str = fecha.strftime('%Y-%m-%d')
        
        habs_ocupadas = []
        for r in reservas:
            if r.fecha_entrada <= fecha <= r.fecha_salida:
                if r.habitacion_id not in habs_ocupadas:
                    habs_ocupadas.append(r.habitacion_id)
        
        habs_disponibles = [h for h in todas_habitaciones if h.id not in habs_ocupadas]
        
        ocupacion_por_dia[fecha_str] = {
            'ocupadas': len(habs_ocupadas),
            'disponibles': len(habs_disponibles),
            'total': total_habitaciones,
            'habitaciones_ocupadas': [{'id': h.id, 'nombre': h.nombre, 'precio_base': h.precio_base} 
                                      for h in todas_habitaciones if h.id in habs_ocupadas],
            'habitaciones_disponibles': [{'id': h.id, 'nombre': h.nombre, 'precio_base': h.precio_base} 
                                         for h in habs_disponibles]
        }
    
    return jsonify({
        'total_dias': fin.day,
        'primer_dia_semana': (inicio.weekday() + 1) % 7,
        'mes': mes, 'año': año,
        'ocupacion_por_dia': ocupacion_por_dia,
        'habitaciones': [{'id': h.id, 'nombre': h.nombre, 'tipo': h.tipo, 'precio_base': h.precio_base} 
                        for h in todas_habitaciones]
    })

# ============================================================
# EXPORTAR
# ============================================================

@app.route('/api/exportar-reservas')
@login_required
def exportar_reservas():
    mes = int(request.args.get('mes', datetime.now().month))
    año = int(request.args.get('año', datetime.now().year))
    inicio_mes = datetime(año, mes, 1).date()
    fin_mes = (datetime(año + 1, 1, 1) if mes == 12 else datetime(año, mes + 1, 1)).date() - timedelta(days=1)
    
    reservas = Reserva.query.filter(
        Reserva.posada_id == current_user.posada_id,
        Reserva.fecha_entrada >= inicio_mes,
        Reserva.fecha_entrada <= fin_mes
    ).order_by(Reserva.fecha_entrada).all()
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Localizador', 'Cliente', 'Teléfono', 'Habitación', 'Check-in', 'Check-out', 'Total USD', 'Estado', 'Pago'])
    for r in reservas:
        hab = db.session.get(Habitacion, r.habitacion_id)
        writer.writerow([r.localizador, r.cliente_nombre, r.cliente_telefono, hab.nombre if hab else 'N/A',
                        str(r.fecha_entrada), str(r.fecha_salida), r.total, r.estado, r.metodo_pago or '-'])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv',
                   headers={'Content-Disposition': f'attachment;filename=Reservas_{mes}_{año}.csv'})

@app.route('/api/exportar-ingresos')
@login_required
def exportar_ingresos():
    mes = int(request.args.get('mes', datetime.now().month))
    año = int(request.args.get('año', datetime.now().year))
    inicio_mes = datetime(año, mes, 1).date()
    fin_mes = (datetime(año + 1, 1, 1) if mes == 12 else datetime(año, mes + 1, 1)).date() - timedelta(days=1)
    
    reservas = Reserva.query.filter(
        Reserva.posada_id == current_user.posada_id,
        Reserva.estado == 'confirmada',
        Reserva.fecha_reserva >= inicio_mes,
        Reserva.fecha_reserva <= fin_mes
    ).order_by(Reserva.fecha_reserva).all()
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Localizador', 'Cliente', 'Teléfono', 'Habitación', 'Check-in', 'Check-out', 'Total USD', 'Pago'])
    total_general = 0
    for r in reservas:
        hab = db.session.get(Habitacion, r.habitacion_id)
        writer.writerow([r.localizador, r.cliente_nombre, r.cliente_telefono, hab.nombre if hab else 'N/A',
                        str(r.fecha_entrada), str(r.fecha_salida), r.total, r.metodo_pago or '-'])
        total_general += r.total
    writer.writerow([])
    writer.writerow(['', '', '', '', '', '', 'TOTAL:', round(total_general, 2)])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv',
                   headers={'Content-Disposition': f'attachment;filename=Ingresos_{mes}_{año}.csv'})

# ============================================================
# REINICIAR BASE DE DATOS
# ============================================================

@app.route('/api/reiniciar-bd')
def reiniciar_bd():
    try:
        db.drop_all()
        db.create_all()
        
        posada = Posada(nombre='Demo-Posadas', direccion='Sistema de gestion de prueba')
        db.session.add(posada)
        db.session.commit()
        
        db.session.add(Usuario(username='admin', password_hash=generate_password_hash('admin123'), rol='admin', posada_id=posada.id))
        db.session.add(Agencia(nombre='Agencia Demo', email='agencia@demo.com', password_hash=generate_password_hash('agencia123'), posada_id=posada.id))
        db.session.add(Configuracion(clave='tiempo_expiracion', valor='40', posada_id=posada.id))
        db.session.commit()
        
        for nombre, tipo, cap, camas, precio in [
            ('Deluxe Vista al Mar', 'matrimonial', 2, '1 cama King', 80),
            ('Familiar Premium', 'familiar', 4, '2 camas Queen', 120),
            ('Economica Standard', 'triple', 3, '1 matrimonial + 1 individual', 50),
        ]:
            db.session.add(Habitacion(nombre=nombre, tipo=tipo, capacidad=cap, camas=camas, 
                                     precio_base=precio, descripcion='Hermosa habitacion', posada_id=posada.id))
        db.session.commit()
        
        return jsonify({
            'message': '✅ Base de datos recreada exitosamente',
            'admin': 'admin / admin123',
            'agencia': 'agencia@demo.com / agencia123'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ============================================================
# INICIALIZACIÓN
# ============================================================

with app.app_context():
    db.create_all()
    if not Usuario.query.filter_by(username='admin').first():
        posada = Posada(nombre='Demo-Posadas', direccion='Sistema de gestion de prueba')
        db.session.add(posada)
        db.session.commit()
        
        db.session.add(Usuario(username='admin', password_hash=generate_password_hash('admin123'), rol='admin', posada_id=posada.id))
        db.session.add(Agencia(nombre='Agencia Demo', email='agencia@demo.com', password_hash=generate_password_hash('agencia123'), posada_id=posada.id))
        db.session.add(Configuracion(clave='tiempo_expiracion', valor='40', posada_id=posada.id))
        db.session.commit()
        
        for nombre, tipo, cap, camas, precio in [
            ('Deluxe Vista al Mar', 'matrimonial', 2, '1 cama King', 80),
            ('Familiar Premium', 'familiar', 4, '2 camas Queen', 120),
            ('Economica Standard', 'triple', 3, '1 matrimonial + 1 individual', 50),
        ]:
            db.session.add(Habitacion(nombre=nombre, tipo=tipo, capacidad=cap, camas=camas, 
                                     precio_base=precio, descripcion='Hermosa habitacion', posada_id=posada.id))
        db.session.commit()
        print("✅ Base de datos inicial creada")

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)