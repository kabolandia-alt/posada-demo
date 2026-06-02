import os
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
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'clave_super_secreta_2024')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'posada.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_admin'

class Posada(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), default='Mi Posada')
    direccion = db.Column(db.String(200))
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(100))
    habitaciones = db.relationship('Habitacion', backref='posada', lazy=True)
    reservas = db.relationship('Reserva', backref='posada', lazy=True)
    tarifas = db.relationship('Tarifa', backref='posada', lazy=True)

class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
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
    fecha_inicio = db.Column(db.Date)
    fecha_fin = db.Column(db.Date)
    posada_id = db.Column(db.Integer, db.ForeignKey('posada.id'))

class Agencia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100))
    email = db.Column(db.String(100))
    password_hash = db.Column(db.String(120))
    activo = db.Column(db.Boolean, default=True)
    posada_id = db.Column(db.Integer, db.ForeignKey('posada.id'))

class BloqueoTemporal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    habitacion_id = db.Column(db.Integer, db.ForeignKey('habitacion.id'))
    fecha_entrada = db.Column(db.Date)
    fecha_salida = db.Column(db.Date)
    agencia_id = db.Column(db.Integer, db.ForeignKey('agencia.id'))
    fecha_bloqueo = db.Column(db.DateTime, default=datetime.utcnow)
    expira_en = db.Column(db.DateTime)
    activo = db.Column(db.Boolean, default=True)

class Configuracion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(50))
    valor = db.Column(db.String(100))
    posada_id = db.Column(db.Integer, db.ForeignKey('posada.id'))

def enviar_email(destinatario, asunto, mensaje):
    # Email desactivado - Se activará con servidor pago
    print(f"📧 Email pendiente para: {destinatario}")
    print(f"   Asunto: {asunto}")
    return True

def cancelar_reservas_expiradas():
    """Cancela reservas 'solo_reserva' que hayan expirado"""
    ahora = datetime.utcnow()
    reservas_expiradas = Reserva.query.filter(
        Reserva.solo_reserva == True,
        Reserva.estado == 'pendiente',
        Reserva.fecha_expiracion < ahora
    ).all()
    
    for r in reservas_expiradas:
        r.estado = 'cancelada'
        r.comentario_rechazo = 'Cancelada automáticamente por tiempo límite'
    
    if reservas_expiradas:
        db.session.commit()
        print(f"⏰ {len(reservas_expiradas)} reservas canceladas por expiración")

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Usuario, int(user_id))

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
            return redirect(url_for('panel_admin'))
    return render_template('admin/login.html')

@app.route('/admin')
@login_required
def panel_admin():
    return render_template('admin/dashboard.html')

@app.route('/admin/logout')
@login_required
def logout_admin():
    logout_user()
    return redirect(url_for('login_admin'))

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
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            imagen = filename
    hab = Habitacion(nombre=nombre, tipo=tipo, capacidad=capacidad, camas=camas,
                     precio_base=precio_base, descripcion=descripcion, servicios=servicios,
                     imagen=imagen, posada_id=current_user.posada_id)
    db.session.add(hab)
    db.session.commit()
    return jsonify({'message': 'Habitacion creada', 'id': hab.id})

@app.route('/api/habitaciones/<int:id>', methods=['PUT'])
@login_required
def actualizar_habitacion(id):
    hab = db.session.get(Habitacion, id)
    if not hab or hab.posada_id != current_user.posada_id:
        return jsonify({'error': 'No encontrada'}), 404
    
    if request.is_json:
        data = request.get_json()
        if 'nombre' in data: hab.nombre = data['nombre']
        if 'tipo' in data: hab.tipo = data['tipo']
        if 'capacidad' in data: hab.capacidad = int(data['capacidad'])
        if 'camas' in data: hab.camas = data['camas']
        if 'precio_base' in data: hab.precio_base = float(data['precio_base'])
        if 'descripcion' in data: hab.descripcion = data['descripcion']
        if 'servicios' in data: hab.servicios = data['servicios']
    else:
        if 'nombre' in request.form: hab.nombre = request.form['nombre']
        if 'tipo' in request.form: hab.tipo = request.form['tipo']
        if 'capacidad' in request.form: hab.capacidad = int(request.form['capacidad'])
        if 'camas' in request.form: hab.camas = request.form['camas']
        if 'precio_base' in request.form: hab.precio_base = float(request.form['precio_base'])
        if 'descripcion' in request.form: hab.descripcion = request.form['descripcion']
        if 'servicios' in request.form: hab.servicios = request.form['servicios']
        
        if 'imagen' in request.files:
            file = request.files['imagen']
            if file and file.filename:
                if hab.imagen:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], hab.imagen)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                filename = secure_filename(file.filename)
                filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                hab.imagen = filename
    
    db.session.commit()
    return jsonify({'message': 'Actualizada correctamente'})

@app.route('/api/habitaciones/<int:id>', methods=['DELETE'])
@login_required
def eliminar_habitacion(id):
    hab = db.session.get(Habitacion, id)
    if hab and hab.posada_id == current_user.posada_id:
        db.session.delete(hab)
        db.session.commit()
        return jsonify({'message': 'Eliminada'})
    return jsonify({'error': 'No encontrada'}), 404

@app.route('/api/disponibilidad/<int:posada_id>')
def verificar_disponibilidad(posada_id):
    try:
        # Cancelar reservas expiradas antes de verificar
        cancelar_reservas_expiradas()
        
        entrada_str = request.args.get('entrada')
        salida_str = request.args.get('salida')
        
        if not entrada_str or not salida_str:
            return jsonify([])
        
        entrada = datetime.strptime(entrada_str, '%Y-%m-%d').date()
        salida = datetime.strptime(salida_str, '%Y-%m-%d').date()
        
        reservas = Reserva.query.filter(
            Reserva.posada_id == posada_id,
            Reserva.estado.in_(['confirmada', 'pago_reportado', 'pendiente']),
            Reserva.fecha_entrada < salida,
            Reserva.fecha_salida > entrada
        ).all()
        
        ocupadas = [r.habitacion_id for r in reservas]
        
        if ocupadas:
            disponibles = Habitacion.query.filter(
                Habitacion.posada_id == posada_id,
                Habitacion.estado == 'disponible',
                ~Habitacion.id.in_(ocupadas)
            ).all()
        else:
            disponibles = Habitacion.query.filter_by(posada_id=posada_id, estado='disponible').all()
        
        dias = max((salida - entrada).days, 1)
        resultado = []
        
        for h in disponibles:
            total = h.precio_base * dias
            resultado.append({
                'id': h.id,
                'nombre': h.nombre,
                'tipo': h.tipo,
                'capacidad': h.capacidad,
                'precio_total': round(total, 2),
                'precio_por_noche': round(total/dias, 2),
                'descripcion': h.descripcion or '',
                'servicios': json.loads(h.servicios) if h.servicios else [],
                'imagen': h.imagen or '',
                'camas': h.camas or ''
            })
        
        return jsonify(resultado)
    
    except Exception as e:
        print(f"Error en disponibilidad: {e}")
        return jsonify([])

@app.route('/api/reservas', methods=['POST'])
def crear_reserva():
    try:
        cliente_nombre = request.form.get('cliente_nombre', '')
        cliente_cedula = request.form.get('cliente_cedula', '')
        cliente_telefono = request.form.get('cliente_telefono', '')
        cliente_email = request.form.get('cliente_email', '')
        fecha_entrada_str = request.form.get('fecha_entrada', '')
        fecha_salida_str = request.form.get('fecha_salida', '')
        adultos = int(request.form.get('adultos', 1))
        ninos = int(request.form.get('ninos', 0))
        metodo_pago = request.form.get('metodo_pago', '')
        datos_huespedes = request.form.get('datos_huespedes', '[]')
        habitacion_id = int(request.form.get('habitacion_id', 0))
        
        if not fecha_entrada_str or not fecha_salida_str:
            return jsonify({'error': 'Fechas requeridas'}), 400
            
        entrada = datetime.strptime(fecha_entrada_str, '%Y-%m-%d').date()
        salida = datetime.strptime(fecha_salida_str, '%Y-%m-%d').date()
        dias = max((salida - entrada).days, 1)
        
        hab = db.session.get(Habitacion, habitacion_id)
        if not hab:
            return jsonify({'error': 'Habitacion no encontrada'}), 404
        
        total = hab.precio_base * dias
        
        comprobante_filename = None
        if metodo_pago not in ['efectivo', 'solo_reserva'] and 'comprobante' in request.files:
            file = request.files['comprobante']
            if file and file.filename and file.filename != '':
                try:
                    filename = secure_filename(file.filename)
                    filename = f"pago_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                    upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(upload_path)
                    comprobante_filename = filename
                except Exception as e:
                    print(f"Error guardando comprobante: {e}")
                    comprobante_filename = None
        
        solo_reserva = metodo_pago == 'solo_reserva'
        estado_inicial = 'pendiente' if solo_reserva else 'pago_reportado'
        
        minutos_expiracion = 40
        if solo_reserva:
            config = Configuracion.query.filter_by(
                posada_id=hab.posada_id, clave='tiempo_expiracion'
            ).first()
            if config:
                minutos_expiracion = int(config.valor)
        fecha_expiracion = datetime.utcnow() + timedelta(minutes=minutos_expiracion) if solo_reserva else None
        
        reserva = Reserva(
            cliente_nombre=cliente_nombre,
            cliente_cedula=cliente_cedula,
            cliente_telefono=cliente_telefono,
            cliente_email=cliente_email,
            fecha_entrada=entrada,
            fecha_salida=salida,
            adultos=adultos,
            ninos=ninos,
            total=round(total, 2),
            habitacion_id=habitacion_id,
            posada_id=hab.posada_id,
            metodo_pago=metodo_pago if not solo_reserva else 'solo_reserva',
            comprobante=comprobante_filename if not solo_reserva else None,
            datos_huespedes=datos_huespedes,
            estado=estado_inicial,
            solo_reserva=solo_reserva,
            fecha_expiracion=fecha_expiracion
        )
        
        db.session.add(reserva)
        db.session.commit()
        
        mensaje_extra = ''
        if solo_reserva:
            mensaje_extra = f'\n\n⏰ IMPORTANTE: Esta reserva expira en {minutos_expiracion} minutos si no se realiza el pago.'
        
        return jsonify({
            'message': 'Reserva creada exitosamente' + mensaje_extra,
            'reserva_id': reserva.id,
            'total': round(total, 2),
            'solo_reserva': solo_reserva
        })
        
    except Exception as e:
        print(f"Error en crear_reserva: {str(e)}")
        db.session.rollback()
        return jsonify({'error': f'Error al crear reserva: {str(e)}'}), 500

@app.route('/api/tarifas', methods=['GET'])
@login_required
def obtener_tarifas():
    tarifas = Tarifa.query.filter_by(posada_id=current_user.posada_id).all()
    return jsonify([{
        'id': t.id, 'nombre': t.nombre, 'tipo': t.tipo,
        'multiplicador': t.multiplicador,
        'fecha_inicio': str(t.fecha_inicio),
        'fecha_fin': str(t.fecha_fin)
    } for t in tarifas])

@app.route('/api/tarifas', methods=['POST'])
@login_required
def crear_tarifa():
    data = request.json
    tarifa = Tarifa(
        nombre=data['nombre'],
        tipo=data.get('tipo', 'temporada_alta'),
        multiplicador=float(data.get('multiplicador', 0)),
        fecha_inicio=datetime.strptime(data['fecha_inicio'], '%Y-%m-%d').date(),
        fecha_fin=datetime.strptime(data['fecha_fin'], '%Y-%m-%d').date(),
        posada_id=current_user.posada_id
    )
    db.session.add(tarifa)
    db.session.commit()
    return jsonify({'message': 'Tarifa creada'})

@app.route('/api/tarifas/<int:id>', methods=['DELETE'])
@login_required
def eliminar_tarifa(id):
    tarifa = db.session.get(Tarifa, id)
    if tarifa and tarifa.posada_id == current_user.posada_id:
        db.session.delete(tarifa)
        db.session.commit()
        return jsonify({'message': 'Tarifa eliminada'})
    return jsonify({'error': 'No encontrada'}), 404

@app.route('/api/calendario-completo')
@login_required
def calendario_completo():
    cancelar_reservas_expiradas()
    
    mes = int(request.args.get('mes', datetime.now().month))
    año = int(request.args.get('año', datetime.now().year))
    inicio = datetime(año, mes, 1).date()
    if mes == 12:
        fin = datetime(año + 1, 1, 1).date() - timedelta(days=1)
    else:
        fin = datetime(año, mes + 1, 1).date() - timedelta(days=1)
    
    total_dias = fin.day
    primer_dia_semana = (inicio.weekday() + 1) % 7
    
    total_habitaciones = Habitacion.query.filter_by(posada_id=current_user.posada_id).count()
    
    reservas = Reserva.query.filter(
        Reserva.posada_id == current_user.posada_id,
        Reserva.estado.in_(['confirmada', 'pago_reportado', 'pendiente']),
        Reserva.fecha_entrada <= fin,
        Reserva.fecha_salida >= inicio
    ).all()
    
    ocupacion_por_dia = {}
    for dia in range(1, total_dias + 1):
        fecha = datetime(año, mes, dia).date()
        fecha_str = fecha.strftime('%Y-%m-%d')
        ocupadas = 0
        for r in reservas:
            if r.fecha_entrada <= fecha <= r.fecha_salida:
                ocupadas += 1
        ocupacion_por_dia[fecha_str] = {
            'ocupadas': ocupadas,
            'disponibles': total_habitaciones - ocupadas,
            'total': total_habitaciones
        }
    
    habitaciones = Habitacion.query.filter_by(posada_id=current_user.posada_id).all()
    reservas_por_hab = {}
    for hab in habitaciones:
        dias_ocupados = []
        for r in reservas:
            if r.habitacion_id == hab.id:
                fecha = max(r.fecha_entrada, inicio)
                while fecha <= min(r.fecha_salida, fin):
                    dias_ocupados.append(fecha.strftime('%Y-%m-%d'))
                    fecha += timedelta(days=1)
        reservas_por_hab[hab.id] = dias_ocupados
    
    return jsonify({
        'total_dias': total_dias,
        'primer_dia_semana': primer_dia_semana,
        'mes': mes,
        'año': año,
        'total_habitaciones': total_habitaciones,
        'ocupacion_por_dia': ocupacion_por_dia,
        'reservas': reservas_por_hab,
        'habitaciones': [{'id': h.id, 'nombre': h.nombre, 'tipo': h.tipo} for h in habitaciones]
    })

@app.route('/api/reservas-pendientes')
@login_required
def reservas_pendientes():
    cancelar_reservas_expiradas()
    
    reservas = Reserva.query.filter_by(
        posada_id=current_user.posada_id
    ).filter(Reserva.estado.in_(['pago_reportado', 'pendiente'])).order_by(Reserva.fecha_reserva.desc()).all()
    return jsonify([{
        'id': r.id, 'cliente_nombre': r.cliente_nombre,
        'cliente_telefono': r.cliente_telefono,
        'cliente_email': r.cliente_email,
        'fecha_entrada': str(r.fecha_entrada),
        'fecha_salida': str(r.fecha_salida),
        'total': r.total, 'metodo_pago': r.metodo_pago,
        'comprobante': r.comprobante,
        'datos_huespedes': r.datos_huespedes,
        'solo_reserva': r.solo_reserva,
        'fecha_expiracion': (r.fecha_expiracion - timedelta(hours=4)).strftime('%d/%m/%Y %H:%M') if r.fecha_expiracion else None,
        'aprobado_por': r.aprobado_por,
        'fecha_aprobacion': (r.fecha_aprobacion - timedelta(hours=4)).strftime('%d/%m/%Y %H:%M') if r.fecha_aprobacion else None,
        'comentario_rechazo': r.comentario_rechazo,
        'fecha_reserva': (r.fecha_reserva - timedelta(hours=4)).strftime('%d/%m/%Y %H:%M')
    } for r in reservas])

@app.route('/api/todas-reservas')
@login_required
def todas_reservas():
    cancelar_reservas_expiradas()
    
    reservas = Reserva.query.filter_by(
        posada_id=current_user.posada_id
    ).order_by(Reserva.fecha_reserva.desc()).all()
    
    resultado = []
    for r in reservas:
        hab = db.session.get(Habitacion, r.habitacion_id)
        resultado.append({
            'id': r.id,
            'cliente_nombre': r.cliente_nombre,
            'cliente_telefono': r.cliente_telefono,
            'cliente_email': r.cliente_email,
            'habitacion_nombre': hab.nombre if hab else 'N/A',
            'fecha_entrada': str(r.fecha_entrada),
            'fecha_salida': str(r.fecha_salida),
            'total': r.total,
            'estado': r.estado,
            'metodo_pago': r.metodo_pago or '-',
            'comprobante': r.comprobante,
            'datos_huespedes': r.datos_huespedes,
            'solo_reserva': r.solo_reserva,
            'fecha_expiracion': (r.fecha_expiracion - timedelta(hours=4)).strftime('%d/%m/%Y %H:%M') if r.fecha_expiracion else None,
            'fecha_reserva': (r.fecha_reserva - timedelta(hours=4)).strftime('%d/%m/%Y %H:%M')
        })
    
    return jsonify(resultado)

@app.route('/api/ingresos-mes')
@login_required
def ingresos_mes():
    mes = int(request.args.get('mes', datetime.now().month))
    año = int(request.args.get('año', datetime.now().year))
    
    inicio_mes = datetime(año, mes, 1).date()
    if mes == 12:
        fin_mes = datetime(año + 1, 1, 1).date() - timedelta(days=1)
    else:
        fin_mes = datetime(año, mes + 1, 1).date() - timedelta(days=1)
    
    reservas = Reserva.query.filter(
        Reserva.posada_id == current_user.posada_id,
        Reserva.estado == 'confirmada',
        Reserva.fecha_reserva >= inicio_mes,
        Reserva.fecha_reserva <= fin_mes
    ).all()
    
    total_ingresos = sum(r.total for r in reservas)
    
    return jsonify({
        'total': round(total_ingresos, 2),
        'cantidad': len(reservas),
        'mes': mes,
        'año': año
    })

@app.route('/api/exportar-reservas')
@login_required
def exportar_reservas():
    cancelar_reservas_expiradas()
    
    mes = int(request.args.get('mes', datetime.now().month))
    año = int(request.args.get('año', datetime.now().year))
    
    inicio_mes = datetime(año, mes, 1).date()
    if mes == 12:
        fin_mes = datetime(año + 1, 1, 1).date() - timedelta(days=1)
    else:
        fin_mes = datetime(año, mes + 1, 1).date() - timedelta(days=1)
    
    reservas = Reserva.query.filter(
        Reserva.posada_id == current_user.posada_id,
        Reserva.fecha_entrada >= inicio_mes,
        Reserva.fecha_entrada <= fin_mes
    ).order_by(Reserva.fecha_entrada).all()
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID Reserva', 'Cliente', 'Teléfono', 'Email', 'Habitación', 'Tipo Hab', 'Check-in', 'Check-out', 'Noches', 'Adultos', 'Niños', 'Total USD', 'Estado', 'Método Pago', 'Fecha Reserva'])
    
    for r in reservas:
        hab = db.session.get(Habitacion, r.habitacion_id)
        noches = (r.fecha_salida - r.fecha_entrada).days if r.fecha_entrada and r.fecha_salida else 0
        writer.writerow([
            r.id,
            r.cliente_nombre,
            r.cliente_telefono,
            r.cliente_email,
            hab.nombre if hab else 'N/A',
            hab.tipo if hab else 'N/A',
            str(r.fecha_entrada),
            str(r.fecha_salida),
            noches,
            r.adultos,
            r.ninos,
            r.total,
            r.estado,
            r.metodo_pago or '-',
            (r.fecha_reserva - timedelta(hours=4)).strftime('%d/%m/%Y') if r.fecha_reserva else ''
        ])
    
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment;filename=Reservas_{mes}_{año}.csv'}
    )

@app.route('/api/exportar-ingresos')
@login_required
def exportar_ingresos():
    mes = int(request.args.get('mes', datetime.now().month))
    año = int(request.args.get('año', datetime.now().year))
    
    inicio_mes = datetime(año, mes, 1).date()
    if mes == 12:
        fin_mes = datetime(año + 1, 1, 1).date() - timedelta(days=1)
    else:
        fin_mes = datetime(año, mes + 1, 1).date() - timedelta(days=1)
    
    reservas = Reserva.query.filter(
        Reserva.posada_id == current_user.posada_id,
        Reserva.estado == 'confirmada',
        Reserva.fecha_reserva >= inicio_mes,
        Reserva.fecha_reserva <= fin_mes
    ).order_by(Reserva.fecha_reserva).all()
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Cliente', 'Teléfono', 'Habitación', 'Check-in', 'Check-out', 'Total USD', 'Método Pago', 'Fecha Pago'])
    
    total_general = 0
    for r in reservas:
        hab = db.session.get(Habitacion, r.habitacion_id)
        writer.writerow([
            r.id,
            r.cliente_nombre,
            r.cliente_telefono,
            hab.nombre if hab else 'N/A',
            str(r.fecha_entrada),
            str(r.fecha_salida),
            r.total,
            r.metodo_pago or '-',
            (r.fecha_reserva - timedelta(hours=4)).strftime('%d/%m/%Y') if r.fecha_reserva else ''
        ])
        total_general += r.total
    
    writer.writerow([])
    writer.writerow(['', '', '', '', '', '', 'TOTAL:', '', round(total_general, 2)])
    
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment;filename=Ingresos_{mes}_{año}.csv'}
    )

@app.route('/api/validar-pago/<int:reserva_id>', methods=['POST'])
@login_required
def validar_pago(reserva_id):
    data = request.json
    reserva = db.session.get(Reserva, reserva_id)
    if reserva and reserva.posada_id == current_user.posada_id:
        accion = data.get('accion', 'confirmada')
        comentario = data.get('comentario', '')
        
        reserva.estado = accion
        reserva.aprobado_por = current_user.username
        reserva.fecha_aprobacion = datetime.utcnow()
        
        if accion == 'cancelada' and comentario:
            reserva.comentario_rechazo = comentario
        
        db.session.commit()
        
        return jsonify({'message': 'Actualizado correctamente'})
    return jsonify({'error': 'No encontrada'}), 404

# ============ CONFIGURACIÓN ============
@app.route('/api/configuracion', methods=['GET'])
@login_required
def obtener_configuracion():
    configs = Configuracion.query.filter_by(posada_id=current_user.posada_id).all()
    resultado = {}
    for c in configs:
        resultado[c.clave] = c.valor
    return jsonify(resultado)

@app.route('/api/configuracion', methods=['POST'])
@login_required
def guardar_configuracion():
    data = request.json
    for clave, valor in data.items():
        config = Configuracion.query.filter_by(
            posada_id=current_user.posada_id, clave=clave
        ).first()
        if config:
            config.valor = str(valor)
        else:
            config = Configuracion(
                clave=clave,
                valor=str(valor),
                posada_id=current_user.posada_id
            )
            db.session.add(config)
    db.session.commit()
    return jsonify({'message': 'Configuración guardada'})

# ============ PORTAL DE AGENCIAS ============
@app.route('/agencia/login', methods=['GET', 'POST'])
def login_agencia():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        agencia = Agencia.query.filter_by(email=email, activo=True).first()
        if agencia and check_password_hash(agencia.password_hash, password):
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
    
    posada_id = 1
    inicio = datetime(año, mes, 1).date()
    if mes == 12:
        fin = datetime(año + 1, 1, 1).date() - timedelta(days=1)
    else:
        fin = datetime(año, mes + 1, 1).date() - timedelta(days=1)
    
    total_habitaciones = Habitacion.query.filter_by(posada_id=posada_id).count()
    
    reservas = Reserva.query.filter(
        Reserva.posada_id == posada_id,
        Reserva.estado.in_(['confirmada', 'pago_reportado', 'pendiente']),
        Reserva.fecha_entrada <= fin,
        Reserva.fecha_salida >= inicio
    ).all()
    
    ocupacion_por_dia = {}
    for dia in range(1, fin.day + 1):
        fecha = datetime(año, mes, dia).date()
        fecha_str = fecha.strftime('%Y-%m-%d')
        ocupadas = 0
        for r in reservas:
            if r.fecha_entrada <= fecha <= r.fecha_salida:
                ocupadas += 1
        ocupacion_por_dia[fecha_str] = {
            'ocupadas': ocupadas,
            'disponibles': total_habitaciones - ocupadas,
            'total': total_habitaciones
        }
    
    return jsonify({
        'total_dias': fin.day,
        'primer_dia_semana': (inicio.weekday() + 1) % 7,
        'mes': mes,
        'año': año,
        'ocupacion_por_dia': ocupacion_por_dia,
        'habitaciones': [{'id': h.id, 'nombre': h.nombre, 'tipo': h.tipo, 'precio_base': h.precio_base} for h in Habitacion.query.filter_by(posada_id=posada_id).all()]
    })

@app.route('/api/reiniciar-bd')
def reiniciar_bd():
    try:
        db.drop_all()
        db.create_all()
        
        posada = Posada(nombre='Demo-Posadas', direccion='Sistema de gestion de prueba')
        db.session.add(posada)
        db.session.commit()
        
        admin = Usuario(username='admin', password_hash=generate_password_hash('admin123'),
                        rol='admin', posada_id=posada.id)
        db.session.add(admin)
        
        agencia = Agencia(nombre='Agencia Demo', email='agencia@demo.com',
                         password_hash=generate_password_hash('agencia123'),
                         posada_id=posada.id)
        db.session.add(agencia)
        
        config_default = Configuracion(clave='tiempo_expiracion', valor='40', posada_id=posada.id)
        db.session.add(config_default)
        db.session.commit()
        
        habs = [
            ('Deluxe Vista al Mar', 'matrimonial', 2, '1 cama King', 80),
            ('Familiar Premium', 'familiar', 4, '2 camas Queen', 120),
            ('Economica Standard', 'triple', 3, '1 matrimonial + 1 individual', 50),
        ]
        for nombre, tipo, cap, camas, precio in habs:
            db.session.add(Habitacion(nombre=nombre, tipo=tipo, capacidad=cap,
                                      camas=camas, precio_base=precio,
                                      descripcion='Hermosa habitacion', posada_id=posada.id))
        db.session.commit()
        
        return jsonify({'message': '✅ Base de datos recreada'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

with app.app_context():
    db.create_all()
    if not Usuario.query.filter_by(username='admin').first():
        posada = Posada(nombre='Demo-Posadas', direccion='Sistema de gestion de prueba')
        db.session.add(posada)
        db.session.commit()
        admin = Usuario(username='admin', password_hash=generate_password_hash('admin123'),
                        rol='admin', posada_id=posada.id)
        db.session.add(admin)
        
        agencia = Agencia(nombre='Agencia Demo', email='agencia@demo.com',
                         password_hash=generate_password_hash('agencia123'),
                         posada_id=posada.id)
        db.session.add(agencia)
        
        config_default = Configuracion(clave='tiempo_expiracion', valor='40', posada_id=posada.id)
        db.session.add(config_default)
        db.session.commit()
        
        habs = [
            ('Deluxe Vista al Mar', 'matrimonial', 2, '1 cama King', 80),
            ('Familiar Premium', 'familiar', 4, '2 camas Queen', 120),
            ('Economica Standard', 'triple', 3, '1 matrimonial + 1 individual', 50),
        ]
        for nombre, tipo, cap, camas, precio in habs:
            db.session.add(Habitacion(nombre=nombre, tipo=tipo, capacidad=cap,
                                      camas=camas, precio_base=precio,
                                      descripcion='Hermosa habitacion', posada_id=posada.id))
        db.session.commit()
        print("✅ Base de datos creada")
        print("👤 admin | 🔑 admin123")
        print("🏢 agencia@demo.com | 🔑 agencia123")

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True, port=5000)