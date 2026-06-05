import os
import random
import string
from functools import wraps
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
    posada_id = db.Column(db.Integer, db.ForeignKey('posada.id'), nullable=True)
    permisos = db.Column(db.Text, default='[]')
    creado_por = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)
    activo = db.Column(db.Boolean, default=True)

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
    estado = db.Column(db.String(20), default='reservado')
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
    while True:
        letras = ''.join(random.choices(string.ascii_uppercase, k=3))
        numeros = ''.join(random.choices(string.digits, k=3))
        localizador = f"{letras}{numeros}"
        hace_3_meses = datetime.utcnow() - timedelta(days=90)
        existe = Reserva.query.filter(
            Reserva.localizador == localizador,
            Reserva.fecha_reserva > hace_3_meses
        ).first()
        if not existe:
            return localizador

def registrar_log(usuario_id, accion, descripcion, posada_id=None):
    try:
        log = LogActividad(
            usuario_id=usuario_id, accion=accion,
            descripcion=descripcion, posada_id=posada_id or 1
        )
        db.session.add(log)
        db.session.commit()
    except:
        pass

def verificar_permiso(usuario, permiso_requerido):
    if usuario.rol == 'super_admin':
        return True
    permisos = json.loads(usuario.permisos) if usuario.permisos else []
    return permiso_requerido in permisos

def cancelar_reservas_expiradas():
    ahora = datetime.utcnow()
    reservas_expiradas = Reserva.query.filter(
        Reserva.solo_reserva == True,
        Reserva.estado == 'reservado',
        Reserva.fecha_expiracion != None,
        Reserva.fecha_expiracion < ahora
    ).all()
    for r in reservas_expiradas:
        r.estado = 'cancelada'
        r.comentario_rechazo = 'Cancelada automáticamente por no confirmar a tiempo'
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
# RUTAS PÚBLICAS
# ============================================================

@app.route('/')
def inicio():
    return render_template('cliente/inicio.html')

# ============================================================
# RUTAS ADMIN
# ============================================================

@app.route('/admin/login', methods=['GET', 'POST'])
def login_admin():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = Usuario.query.filter_by(username=username, activo=True).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            registrar_log(user.id, 'login', f'Inicio de sesión: {user.username} ({user.rol})')
            if user.rol == 'super_admin':
                return redirect(url_for('panel_super_admin'))
            else:
                return redirect(url_for('panel_admin'))
        return render_template('admin/login.html', error='Usuario o contraseña incorrectos')
    return render_template('admin/login.html')

@app.route('/admin')
@login_required
def panel_admin():
    if current_user.rol == 'super_admin':
        return redirect(url_for('panel_super_admin'))
    return render_template('admin/dashboard.html')

@app.route('/super-admin')
@login_required
def panel_super_admin():
    if current_user.rol != 'super_admin':
        return redirect(url_for('panel_admin'))
    return render_template('admin/super_admin.html')

@app.route('/admin/logout')
@login_required
def logout_admin():
    registrar_log(current_user.id, 'logout', f'Cierre de sesión: {current_user.username}')
    logout_user()
    return redirect(url_for('login_admin'))

@app.route('/api/verificar-rol')
@login_required
def verificar_rol():
    posada = db.session.get(Posada, current_user.posada_id) if current_user.posada_id else None
    return jsonify({
        'rol': current_user.rol, 
        'username': current_user.username,
        'posada_id': current_user.posada_id,
        'color_primario': posada.color_primario if posada else '#2C5F8A',
        'color_secundario': posada.color_secundario if posada else '#51CF66'
    })

# ============================================================
# API HABITACIONES
# ============================================================

@app.route('/api/habitaciones', methods=['GET'])
@login_required
def obtener_habitaciones():
    cancelar_reservas_expiradas()
    posada_id = current_user.posada_id if current_user.posada_id else 1
    habitaciones = Habitacion.query.filter_by(posada_id=posada_id).all()
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
        posada_id = current_user.posada_id if current_user.posada_id else 1
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
            imagen=imagen, posada_id=posada_id
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
    if not hab:
        return jsonify({'error': 'No encontrada'}), 404
    try:
        if request.is_json:
            data = request.get_json()
            for campo in ['nombre', 'tipo', 'capacidad', 'camas', 'precio_base', 'descripcion', 'servicios']:
                if campo in data:
                    setattr(hab, campo, data[campo])
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
    if hab:
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
        minutos_expiracion = 40
        if solo_reserva:
            config = Configuracion.query.filter_by(posada_id=hab.posada_id, clave='tiempo_expiracion').first()
            if config:
                try:
                    minutos_expiracion = int(config.valor)
                except:
                    minutos_expiracion = 40
        expiracion = datetime.utcnow() + timedelta(minutes=minutos_expiracion) if solo_reserva else None
        localizador = generar_localizador(hab.posada_id)
        
        estado_inicial = 'reservado' if solo_reserva else 'pago_pendiente'
        
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
            metodo_pago=metodo_pago, comprobante=comprobante,
            datos_huespedes=datos.get('datos_huespedes', '[]'),
            estado=estado_inicial,
            solo_reserva=solo_reserva, fecha_expiracion=expiracion
        )
        db.session.add(reserva)
        db.session.commit()
        registrar_log(1, 'nueva_reserva', f'Nueva reserva: {localizador} - {hab.nombre} ({estado_inicial})')
        return jsonify({
            'message': 'Reserva creada exitosamente',
            'reserva_id': reserva.id,
            'localizador': reserva.localizador,
            'total': round(total, 2),
            'estado': estado_inicial
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/pagar-reserva', methods=['POST'])
def pagar_reserva():
    """Cliente paga una reserva existente"""
    try:
        localizador = request.form.get('localizador')
        metodo_pago = request.form.get('metodo_pago', 'zelle')
        
        reserva = Reserva.query.filter_by(localizador=localizador.upper()).first()
        if not reserva:
            return jsonify({'error': 'Reserva no encontrada'}), 404
        
        comprobante = None
        if metodo_pago != 'efectivo' and 'comprobante' in request.files:
            file = request.files['comprobante']
            if file and file.filename:
                filename = secure_filename(file.filename)
                filename = f"pago_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                comprobante = filename
        
        reserva.metodo_pago = metodo_pago
        reserva.comprobante = comprobante
        reserva.estado = 'pago_pendiente'
        reserva.fecha_expiracion = None
        reserva.solo_reserva = False
        
        db.session.commit()
        registrar_log(1, 'pago_reserva', f'Cliente pagó reserva: {localizador} - {metodo_pago}')
        
        return jsonify({
            'message': 'Pago registrado exitosamente',
            'localizador': reserva.localizador,
            'estado': reserva.estado
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/consultar-reserva/<localizador>')
def consultar_reserva_por_localizador(localizador):
    try:
        reserva = Reserva.query.filter_by(localizador=localizador.upper()).first()
        if not reserva:
            return jsonify({'error': 'Reserva no encontrada'}), 404
        hab = db.session.get(Habitacion, reserva.habitacion_id)
        return jsonify({
            'localizador': reserva.localizador,
            'cliente_nombre': reserva.cliente_nombre,
            'fecha_entrada': str(reserva.fecha_entrada),
            'fecha_salida': str(reserva.fecha_salida),
            'adultos': reserva.adultos, 'ninos': reserva.ninos,
            'total': reserva.total, 'estado': reserva.estado,
            'metodo_pago': reserva.metodo_pago,
            'habitacion': hab.nombre if hab else 'N/A',
            'fecha_reserva': (reserva.fecha_reserva - timedelta(hours=4)).strftime('%d/%m/%Y %H:%M')
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reservas/<int:reserva_id>', methods=['PUT'])
@login_required
def editar_reserva(reserva_id):
    if current_user.rol not in ['super_admin', 'admin', 'manager']:
        return jsonify({'error': 'No autorizado'}), 403
    reserva = db.session.get(Reserva, reserva_id)
    if not reserva:
        return jsonify({'error': 'Reserva no encontrada'}), 404
    try:
        data = request.json
        campos_permitidos = ['cliente_nombre', 'cliente_telefono', 'cliente_email', 
                            'estado', 'total', 'adultos', 'ninos', 'metodo_pago', 'habitacion_id']
        for campo in campos_permitidos:
            if campo in data:
                if campo in ['total']: setattr(reserva, campo, float(data[campo]))
                elif campo in ['adultos', 'ninos', 'habitacion_id']: setattr(reserva, campo, int(data[campo]))
                else: setattr(reserva, campo, data[campo])
        if 'fecha_entrada' in data:
            reserva.fecha_entrada = datetime.strptime(data['fecha_entrada'], '%Y-%m-%d').date()
        if 'fecha_salida' in data:
            reserva.fecha_salida = datetime.strptime(data['fecha_salida'], '%Y-%m-%d').date()
        if 'datos_huespedes' in data:
            reserva.datos_huespedes = json.dumps(data['datos_huespedes'])
        if 'estado' in data and data['estado'] == 'confirmada':
            reserva.fecha_expiracion = None
            reserva.solo_reserva = False
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
    posada_id = current_user.posada_id if current_user.posada_id else 1
    tarifas = Tarifa.query.filter_by(posada_id=posada_id).all()
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
        posada_id = current_user.posada_id if current_user.posada_id else 1
        tarifa = Tarifa(
            nombre=data['nombre'], tipo=data.get('tipo', 'rango_fechas'),
            multiplicador=float(data.get('multiplicador', 0)),
            fecha_inicio=datetime.strptime(data['fecha_inicio'], '%Y-%m-%d').date() if data.get('fecha_inicio') else None,
            fecha_fin=datetime.strptime(data['fecha_fin'], '%Y-%m-%d').date() if data.get('fecha_fin') else None,
            dias_aplicacion=data.get('dias_aplicacion'), posada_id=posada_id
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
    if tarifa:
        nombre = tarifa.nombre
        db.session.delete(tarifa)
        db.session.commit()
        registrar_log(current_user.id, 'eliminar_tarifa', f'Eliminó tarifa: {nombre}')
        return jsonify({'message': 'Tarifa eliminada'})
    return jsonify({'error': 'No encontrada'}), 404

# ============================================================
# API DASHBOARD Y GRÁFICOS
# ============================================================

@app.route('/api/calendario-completo')
@login_required
def calendario_completo():
    cancelar_reservas_expiradas()
    posada_id = current_user.posada_id if current_user.posada_id else 1
    mes = int(request.args.get('mes', datetime.now().month))
    año = int(request.args.get('año', datetime.now().year))
    inicio = datetime(año, mes, 1).date()
    fin = (datetime(año + 1, 1, 1) if mes == 12 else datetime(año, mes + 1, 1)).date() - timedelta(days=1)
    total_habitaciones = Habitacion.query.filter_by(posada_id=posada_id).count()
    reservas = Reserva.query.filter(
        Reserva.posada_id == posada_id, Reserva.estado != 'cancelada',
        Reserva.fecha_entrada <= fin, Reserva.fecha_salida >= inicio
    ).all()
    ocupacion_por_dia = {}
    for dia in range(1, fin.day + 1):
        fecha = datetime(año, mes, dia).date()
        ocupadas = sum(1 for r in reservas if r.fecha_entrada <= fecha <= r.fecha_salida)
        ocupacion_por_dia[fecha.strftime('%Y-%m-%d')] = {
            'ocupadas': ocupadas, 'disponibles': total_habitaciones - ocupadas, 'total': total_habitaciones
        }
    return jsonify({
        'total_dias': fin.day, 'primer_dia_semana': (inicio.weekday() + 1) % 7,
        'mes': mes, 'año': año, 'total_habitaciones': total_habitaciones,
        'ocupacion_por_dia': ocupacion_por_dia,
        'habitaciones': [{'id': h.id, 'nombre': h.nombre, 'tipo': h.tipo} for h in Habitacion.query.filter_by(posada_id=posada_id).all()]
    })

@app.route('/api/reservas-pendientes')
@login_required
def reservas_pendientes():
    """SOLO para Validar Pagos: muestra reservas en estado pago_pendiente"""
    cancelar_reservas_expiradas()
    posada_id = current_user.posada_id if current_user.posada_id else 1
    reservas = Reserva.query.filter_by(posada_id=posada_id).filter(
        Reserva.estado == 'pago_pendiente'
    ).order_by(Reserva.fecha_reserva.desc()).all()
    resultado = []
    for r in reservas:
        hab = db.session.get(Habitacion, r.habitacion_id)
        resultado.append({
            'id': r.id, 'localizador': r.localizador, 'cliente_nombre': r.cliente_nombre,
            'cliente_telefono': r.cliente_telefono or 'No registrado',
            'cliente_email': r.cliente_email or 'No registrado',
            'habitacion_nombre': hab.nombre if hab else 'N/A',
            'fecha_entrada': str(r.fecha_entrada), 'fecha_salida': str(r.fecha_salida),
            'total': r.total, 'estado': r.estado, 'metodo_pago': r.metodo_pago or '-',
            'comprobante': r.comprobante, 'solo_reserva': r.solo_reserva,
            'fecha_expiracion': None,
            'aprobado_por': r.aprobado_por,
            'fecha_aprobacion': None,
            'comentario_rechazo': r.comentario_rechazo,
            'fecha_reserva': (r.fecha_reserva - timedelta(hours=4)).strftime('%d/%m/%Y %H:%M')
        })
    return jsonify(resultado)

@app.route('/api/todas-reservas')
@login_required
def todas_reservas():
    """TODAS las reservas para la sección Reservas"""
    cancelar_reservas_expiradas()
    posada_id = current_user.posada_id if current_user.posada_id else 1
    reservas = Reserva.query.filter_by(posada_id=posada_id).order_by(Reserva.fecha_reserva.desc()).all()
    resultado = []
    for r in reservas:
        hab = db.session.get(Habitacion, r.habitacion_id)
        expiracion = (r.fecha_expiracion - timedelta(hours=4)).strftime('%d/%m/%Y %H:%M') if r.fecha_expiracion else None
        fecha_aprob = (r.fecha_aprobacion - timedelta(hours=4)).strftime('%d/%m/%Y %H:%M') if r.fecha_aprobacion else None
        huespedes = []
        try:
            if r.datos_huespedes:
                huespedes = json.loads(r.datos_huespedes)
        except:
            huespedes = []
        resultado.append({
            'id': r.id, 'localizador': r.localizador, 'cliente_nombre': r.cliente_nombre,
            'cliente_telefono': r.cliente_telefono or 'No registrado',
            'cliente_email': r.cliente_email or 'No registrado',
            'cliente_cedula': r.cliente_cedula or '',
            'habitacion_nombre': hab.nombre if hab else 'N/A', 'habitacion_id': r.habitacion_id,
            'fecha_entrada': str(r.fecha_entrada), 'fecha_salida': str(r.fecha_salida),
            'total': r.total, 'adultos': r.adultos, 'ninos': r.ninos,
            'estado': r.estado, 'metodo_pago': r.metodo_pago or '-',
            'solo_reserva': r.solo_reserva, 'fecha_expiracion': expiracion,
            'aprobado_por': r.aprobado_por, 'fecha_aprobacion': fecha_aprob,
            'comentario_rechazo': r.comentario_rechazo,
            'huespedes': huespedes,
            'fecha_reserva': (r.fecha_reserva - timedelta(hours=4)).strftime('%d/%m/%Y %H:%M')
        })
    return jsonify(resultado)

@app.route('/api/reservas-historicas')
@login_required
def reservas_historicas():
    if current_user.rol not in ['super_admin', 'admin']:
        return jsonify({'error': 'No autorizado'}), 403
    posada_id = current_user.posada_id if current_user.posada_id else 1
    hace_3_meses = datetime.utcnow() - timedelta(days=90)
    reservas = Reserva.query.filter(
        Reserva.posada_id == posada_id,
        Reserva.fecha_reserva < hace_3_meses
    ).order_by(Reserva.fecha_reserva.desc()).limit(500).all()
    resultado = []
    for r in reservas:
        hab = db.session.get(Habitacion, r.habitacion_id)
        resultado.append({
            'localizador': r.localizador, 'cliente_nombre': r.cliente_nombre,
            'cliente_telefono': r.cliente_telefono or '-',
            'habitacion_nombre': hab.nombre if hab else 'N/A',
            'fecha_entrada': str(r.fecha_entrada), 'fecha_salida': str(r.fecha_salida),
            'total': r.total, 'estado': r.estado, 'metodo_pago': r.metodo_pago or '-',
            'comentario_rechazo': r.comentario_rechazo or '',
            'fecha_reserva': (r.fecha_reserva - timedelta(hours=4)).strftime('%d/%m/%Y %H:%M'),
            'fecha_aprobacion': (r.fecha_aprobacion - timedelta(hours=4)).strftime('%d/%m/%Y %H:%M') if r.fecha_aprobacion else None
        })
    return jsonify(resultado)

@app.route('/api/ingresos-mes')
@login_required
def ingresos_mes():
    posada_id = current_user.posada_id if current_user.posada_id else 1
    mes = int(request.args.get('mes', datetime.now().month))
    año = int(request.args.get('año', datetime.now().year))
    inicio_mes = datetime(año, mes, 1).date()
    fin_mes = (datetime(año + 1, 1, 1) if mes == 12 else datetime(año, mes + 1, 1)).date() - timedelta(days=1)
    reservas = Reserva.query.filter(
        Reserva.posada_id == posada_id, Reserva.estado == 'confirmada',
        Reserva.fecha_entrada >= inicio_mes, Reserva.fecha_entrada <= fin_mes
    ).all()
    return jsonify({'total': round(sum(r.total for r in reservas), 2), 'cantidad': len(reservas)})

@app.route('/api/indicadores-dashboard')
@login_required
def indicadores_dashboard():
    try:
        posada_id = current_user.posada_id if current_user.posada_id else 1
        ahora = datetime.utcnow()
        hace_90_dias = ahora - timedelta(days=90)
        reservas_90d = Reserva.query.filter(
            Reserva.posada_id == posada_id, Reserva.estado == 'confirmada',
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
        ocupacion_por_mes = {}
        nombres_meses = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']
        for r in reservas_90d:
            mes = r.fecha_entrada.month
            ocupacion_por_mes[mes] = ocupacion_por_mes.get(mes, 0) + 1
        mejor_mes = max(ocupacion_por_mes.items(), key=lambda x: x[1]) if ocupacion_por_mes else None
        hoy = ahora.date()
        ocupadas_hoy = Reserva.query.filter(
            Reserva.posada_id == posada_id, Reserva.estado != 'cancelada',
            Reserva.fecha_entrada <= hoy, Reserva.fecha_salida >= hoy
        ).count()
        total_habitaciones = Habitacion.query.filter_by(posada_id=posada_id).count()
        return jsonify({
            'mas_vendida': {'nombre': mas_vendida[0], 'reservas': mas_vendida[1]['cantidad'], 'ingresos': round(mas_vendida[1]['ingresos'], 2)} if mas_vendida else None,
            'menos_vendida': {'nombre': menos_vendida[0], 'reservas': menos_vendida[1]['cantidad'], 'ingresos': round(menos_vendida[1]['ingresos'], 2)} if menos_vendida else None,
            'mejor_temporada': {'mes': nombres_meses[mejor_mes[0]-1], 'reservas': mejor_mes[1]} if mejor_mes else None,
            'ocupacion_hoy': {'ocupadas': ocupadas_hoy, 'total': total_habitaciones, 'porcentaje': round((ocupadas_hoy / total_habitaciones * 100) if total_habitaciones > 0 else 0, 1)},
            'total_reservas_90d': len(reservas_90d)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/graficos-dashboard')
@login_required
def graficos_dashboard():
    try:
        posada_id = current_user.posada_id if current_user.posada_id else 1
        ahora = datetime.utcnow()
        hace_90_dias = ahora - timedelta(days=90)
        reservas = Reserva.query.filter(
            Reserva.posada_id == posada_id, Reserva.estado == 'confirmada',
            Reserva.fecha_reserva >= hace_90_dias
        ).all()
        habs = Habitacion.query.filter_by(posada_id=posada_id).all()
        habs_nombres = [h.nombre for h in habs]
        habs_reservas = [sum(1 for r in reservas if r.habitacion_id == h.id) for h in habs]
        meses_nombres = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
        meses_reservas = [0]*12
        for r in reservas:
            meses_reservas[r.fecha_reserva.month-1] += 1
        pagos_data = {}
        for r in reservas:
            metodo = r.metodo_pago or 'Otro'
            pagos_data[metodo] = pagos_data.get(metodo, 0) + r.total
        dias_semana = [0]*7
        for r in reservas:
            dias_semana[r.fecha_entrada.weekday()] += 1
        return jsonify({
            'habitaciones_nombres': habs_nombres, 'habitaciones_reservas': habs_reservas,
            'meses_nombres': meses_nombres, 'meses_reservas': meses_reservas,
            'pagos_nombres': list(pagos_data.keys()), 'pagos_ingresos': [round(v,2) for v in pagos_data.values()],
            'dias_semana': dias_semana
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================
# GESTIÓN DE USUARIOS
# ============================================================

@app.route('/api/usuarios', methods=['GET'])
@login_required
def listar_usuarios():
    if current_user.rol == 'super_admin':
        usuarios = Usuario.query.all()
    else:
        posada_id = current_user.posada_id if current_user.posada_id else 1
        usuarios = Usuario.query.filter_by(posada_id=posada_id).all()
    return jsonify([{
        'id': u.id, 'username': u.username, 'rol': u.rol,
        'posada_id': u.posada_id, 'activo': u.activo,
        'permisos': json.loads(u.permisos) if u.permisos else [],
        'creado_por': u.creado_por
    } for u in usuarios])

@app.route('/api/usuarios', methods=['POST'])
@login_required
def crear_usuario():
    try:
        data = request.json
        if current_user.rol == 'super_admin':
            posada_id = data.get('posada_id')
        elif current_user.rol == 'admin':
            posada_id = current_user.posada_id
        else:
            return jsonify({'error': 'No tienes permisos para crear usuarios'}), 403
        if Usuario.query.filter_by(username=data['username']).first():
            return jsonify({'error': 'El usuario ya existe'}), 400
        roles_permitidos = {
            'super_admin': ['admin', 'manager', 'recepcionista', 'contador'],
            'admin': ['manager', 'recepcionista', 'contador'],
            'manager': ['recepcionista', 'contador']
        }
        rol = data.get('rol', 'recepcionista')
        if rol not in roles_permitidos.get(current_user.rol, []):
            return jsonify({'error': f'No puedes crear usuarios con rol: {rol}'}), 403
        permisos_default = {
            'admin': ['ver_todo', 'editar_todo', 'crear_usuarios', 'eliminar', 'exportar'],
            'manager': ['ver_reservas', 'editar_reservas', 'ver_ingresos', 'exportar', 'validar_pagos', 'check_in'],
            'recepcionista': ['ver_reservas', 'crear_reservas', 'check_in', 'validar_pagos'],
            'contador': ['ver_ingresos', 'exportar', 'ver_reservas']
        }
        permisos = data.get('permisos', permisos_default.get(rol, []))
        usuario = Usuario(
            username=data['username'],
            password_hash=generate_password_hash(data.get('password', 'cambiar123')),
            rol=rol, posada_id=posada_id,
            permisos=json.dumps(permisos), creado_por=current_user.id
        )
        db.session.add(usuario)
        db.session.commit()
        registrar_log(current_user.id, 'crear_usuario', f'Creó usuario: {usuario.username} ({rol})')
        return jsonify({'message': '✅ Usuario creado', 'usuario': usuario.username, 'rol': rol})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/usuarios/<int:usuario_id>', methods=['PUT'])
@login_required
def editar_usuario(usuario_id):
    if current_user.rol not in ['super_admin', 'admin']:
        return jsonify({'error': 'No autorizado'}), 403
    usuario = db.session.get(Usuario, usuario_id)
    if not usuario:
        return jsonify({'error': 'Usuario no encontrado'}), 404
    if current_user.rol != 'super_admin' and usuario.posada_id != current_user.posada_id:
        return jsonify({'error': 'No autorizado'}), 403
    try:
        data = request.json
        if 'permisos' in data:
            usuario.permisos = json.dumps(data['permisos'])
        if 'activo' in data:
            usuario.activo = data['activo']
        if 'rol' in data:
            usuario.rol = data['rol']
        if 'password' in data and data['password']:
            usuario.password_hash = generate_password_hash(data['password'])
        db.session.commit()
        registrar_log(current_user.id, 'editar_usuario', f'Editó usuario: {usuario.username}')
        return jsonify({'message': 'Usuario actualizado correctamente'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/usuarios/<int:usuario_id>', methods=['DELETE'])
@login_required
def eliminar_usuario(usuario_id):
    if current_user.rol not in ['super_admin', 'admin']:
        return jsonify({'error': 'No autorizado'}), 403
    usuario = db.session.get(Usuario, usuario_id)
    if not usuario:
        return jsonify({'error': 'Usuario no encontrado'}), 404
    if usuario.id == current_user.id:
        return jsonify({'error': 'No puedes eliminarte a ti mismo'}), 400
    if current_user.rol != 'super_admin' and usuario.posada_id != current_user.posada_id:
        return jsonify({'error': 'No autorizado'}), 403
    usuario.activo = False
    db.session.commit()
    registrar_log(current_user.id, 'eliminar_usuario', f'Desactivó usuario: {usuario.username}')
    return jsonify({'message': 'Usuario desactivado correctamente'})

# ============================================================
# GESTIÓN DE POSADAS (SOLO SUPER ADMIN)
# ============================================================

@app.route('/api/posadas', methods=['GET'])
@login_required
def listar_posadas():
    if current_user.rol != 'super_admin':
        return jsonify({'error': 'No autorizado'}), 403
    posadas = Posada.query.all()
    return jsonify([{
        'id': p.id, 'nombre': p.nombre, 'direccion': p.direccion,
        'telefono': p.telefono, 'email': p.email, 'activo': p.activo,
        'habitaciones': Habitacion.query.filter_by(posada_id=p.id).count(),
        'reservas': Reserva.query.filter_by(posada_id=p.id).count()
    } for p in posadas])

@app.route('/api/posadas', methods=['POST'])
def registrar_posada():
    try:
        data = request.json
        if Posada.query.filter_by(email=data.get('email')).first():
            return jsonify({'error': 'Ya existe una posada con ese email'}), 400
        posada = Posada(
            nombre=data['nombre'], direccion=data.get('direccion', ''),
            telefono=data.get('telefono', ''), email=data.get('email', ''),
            color_primario=data.get('color_primario', '#2C5F8A'),
            color_secundario=data.get('color_secundario', '#51CF66')
        )
        db.session.add(posada)
        db.session.commit()
        db.session.add(Usuario(
            username='admin_' + str(posada.id),
            password_hash=generate_password_hash('admin123'),
            rol='admin', posada_id=posada.id,
            permisos=json.dumps(['ver_todo', 'editar_todo', 'crear_usuarios', 'eliminar', 'exportar'])
        ))
        db.session.add(Configuracion(clave='tiempo_expiracion', valor='40', posada_id=posada.id))
        db.session.commit()
        registrar_log(1, 'registrar_posada', f'Registró posada: {posada.nombre}')
        return jsonify({
            'message': '✅ Posada registrada',
            'posada_id': posada.id, 'nombre': posada.nombre,
            'admin_usuario': 'admin_' + str(posada.id), 'admin_password': 'admin123'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ============================================================
# LOGS, PAGOS, CONFIGURACIÓN
# ============================================================

@app.route('/api/logs')
@login_required
def ver_logs():
    if current_user.rol not in ['super_admin', 'admin']:
        return jsonify({'error': 'No autorizado'}), 403
    logs = LogActividad.query.order_by(LogActividad.fecha.desc()).limit(100).all()
    return jsonify([{
        'id': log.id,
        'usuario': db.session.get(Usuario, log.usuario_id).username if log.usuario_id else 'Sistema',
        'accion': log.accion, 'descripcion': log.descripcion,
        'fecha': (log.fecha - timedelta(hours=4)).strftime('%d/%m/%Y %H:%M:%S')
    } for log in logs])

@app.route('/api/validar-pago/<int:reserva_id>', methods=['POST'])
@login_required
def validar_pago(reserva_id):
    data = request.json
    reserva = db.session.get(Reserva, reserva_id)
    if reserva:
        accion = data.get('accion', 'confirmada')
        reserva.estado = accion
        reserva.aprobado_por = current_user.username
        reserva.fecha_aprobacion = datetime.utcnow()
        if accion == 'confirmada':
            reserva.fecha_expiracion = None
            reserva.solo_reserva = False
        if accion == 'cancelada':
            reserva.comentario_rechazo = data.get('comentario', '')
            reserva.fecha_expiracion = None
        db.session.commit()
        registrar_log(current_user.id, 'validar_pago', f'{accion} reserva {reserva.localizador}')
        return jsonify({'message': 'Actualizado'})
    return jsonify({'error': 'No encontrada'}), 404

@app.route('/api/configuracion', methods=['GET'])
@login_required
def obtener_configuracion():
    posada_id = current_user.posada_id if current_user.posada_id else 1
    configs = Configuracion.query.filter_by(posada_id=posada_id).all()
    posada = db.session.get(Posada, posada_id)
    return jsonify({
        'configuracion': {c.clave: c.valor for c in configs},
        'posada': {
            'nombre': posada.nombre, 'direccion': posada.direccion,
            'telefono': posada.telefono, 'email': posada.email,
            'color_primario': posada.color_primario, 'color_secundario': posada.color_secundario
        } if posada else None
    })

@app.route('/api/configuracion', methods=['POST'])
@login_required
def guardar_configuracion():
    data = request.json
    posada_id = current_user.posada_id if current_user.posada_id else 1
    if 'configuracion' in data:
        for clave, valor in data['configuracion'].items():
            config = Configuracion.query.filter_by(posada_id=posada_id, clave=clave).first()
            if config: config.valor = str(valor)
            else: db.session.add(Configuracion(clave=clave, valor=str(valor), posada_id=posada_id))
    if 'posada' in data:
        posada = db.session.get(Posada, posada_id)
        if posada:
            for campo in ['nombre', 'direccion', 'telefono', 'email', 'color_primario', 'color_secundario']:
                if campo in data['posada']:
                    setattr(posada, campo, data['posada'][campo])
    db.session.commit()
    registrar_log(current_user.id, 'guardar_configuracion', 'Actualizó configuración')
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
        Reserva.posada_id == 1, Reserva.estado != 'cancelada',
        Reserva.fecha_entrada <= fin, Reserva.fecha_salida >= inicio
    ).all()
    ocupacion_por_dia = {}
    for dia in range(1, fin.day + 1):
        fecha = datetime(año, mes, dia).date()
        habs_ocupadas = [r.habitacion_id for r in reservas if r.fecha_entrada <= fecha <= r.fecha_salida]
        habs_disponibles = [h for h in todas_habitaciones if h.id not in habs_ocupadas]
        ocupacion_por_dia[fecha.strftime('%Y-%m-%d')] = {
            'ocupadas': len(habs_ocupadas), 'disponibles': len(habs_disponibles), 'total': total_habitaciones,
            'habitaciones_ocupadas': [{'id': h.id, 'nombre': h.nombre, 'precio_base': h.precio_base} for h in todas_habitaciones if h.id in habs_ocupadas],
            'habitaciones_disponibles': [{'id': h.id, 'nombre': h.nombre, 'precio_base': h.precio_base} for h in habs_disponibles]
        }
    return jsonify({
        'total_dias': fin.day, 'primer_dia_semana': (inicio.weekday() + 1) % 7,
        'mes': mes, 'año': año, 'ocupacion_por_dia': ocupacion_por_dia,
        'habitaciones': [{'id': h.id, 'nombre': h.nombre, 'tipo': h.tipo, 'precio_base': h.precio_base} for h in todas_habitaciones]
    })

# ============================================================
# EXPORTAR
# ============================================================

@app.route('/api/exportar-reservas')
@login_required
def exportar_reservas():
    posada_id = current_user.posada_id if current_user.posada_id else 1
    mes = int(request.args.get('mes', datetime.now().month))
    año = int(request.args.get('año', datetime.now().year))
    inicio_mes = datetime(año, mes, 1).date()
    fin_mes = (datetime(año + 1, 1, 1) if mes == 12 else datetime(año, mes + 1, 1)).date() - timedelta(days=1)
    reservas = Reserva.query.filter(
        Reserva.posada_id == posada_id, Reserva.fecha_entrada >= inicio_mes, Reserva.fecha_entrada <= fin_mes
    ).order_by(Reserva.fecha_entrada).all()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Localizador','Cliente','Teléfono','Habitación','Check-in','Check-out','Total USD','Estado','Pago'])
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
    posada_id = current_user.posada_id if current_user.posada_id else 1
    mes = int(request.args.get('mes', datetime.now().month))
    año = int(request.args.get('año', datetime.now().year))
    inicio_mes = datetime(año, mes, 1).date()
    fin_mes = (datetime(año + 1, 1, 1) if mes == 12 else datetime(año, mes + 1, 1)).date() - timedelta(days=1)
    reservas = Reserva.query.filter(
        Reserva.posada_id == posada_id, Reserva.estado == 'confirmada',
        Reserva.fecha_reserva >= inicio_mes, Reserva.fecha_reserva <= fin_mes
    ).order_by(Reserva.fecha_reserva).all()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Localizador','Cliente','Teléfono','Habitación','Check-in','Check-out','Total USD','Pago'])
    total_general = 0
    for r in reservas:
        hab = db.session.get(Habitacion, r.habitacion_id)
        writer.writerow([r.localizador, r.cliente_nombre, r.cliente_telefono, hab.nombre if hab else 'N/A',
                        str(r.fecha_entrada), str(r.fecha_salida), r.total, r.metodo_pago or '-'])
        total_general += r.total
    writer.writerow([])
    writer.writerow(['','','','','','','TOTAL:', round(total_general, 2)])
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
        
        db.session.add(Usuario(
            username='super_admin', password_hash=generate_password_hash('admin123'),
            rol='super_admin', posada_id=None,
            permisos=json.dumps(['ver_todo', 'crear_posadas', 'eliminar_todo', 'gestionar_usuarios'])
        ))
        
        posada = Posada(nombre='Demo-Posadas', direccion='Sistema de gestion de prueba')
        db.session.add(posada)
        db.session.commit()
        
        db.session.add(Usuario(
            username='admin', password_hash=generate_password_hash('admin123'),
            rol='admin', posada_id=posada.id,
            permisos=json.dumps(['ver_todo', 'editar_todo', 'crear_usuarios', 'eliminar', 'exportar'])
        ))
        db.session.add(Agencia(nombre='Agencia Demo', email='agencia@demo.com',
                              password_hash=generate_password_hash('agencia123'), posada_id=posada.id))
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
            'super_admin': 'super_admin / admin123',
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
    if not Usuario.query.filter_by(username='super_admin').first():
        db.session.add(Usuario(
            username='super_admin', password_hash=generate_password_hash('admin123'),
            rol='super_admin', posada_id=None,
            permisos=json.dumps(['ver_todo', 'crear_posadas', 'eliminar_todo', 'gestionar_usuarios'])
        ))
        posada = Posada(nombre='Demo-Posadas', direccion='Sistema de gestion de prueba')
        db.session.add(posada)
        db.session.commit()
        db.session.add(Usuario(
            username='admin', password_hash=generate_password_hash('admin123'),
            rol='admin', posada_id=posada.id,
            permisos=json.dumps(['ver_todo', 'editar_todo', 'crear_usuarios', 'eliminar', 'exportar'])
        ))
        db.session.add(Agencia(nombre='Agencia Demo', email='agencia@demo.com',
                              password_hash=generate_password_hash('agencia123'), posada_id=posada.id))
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