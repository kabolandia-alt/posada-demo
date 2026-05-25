import os
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import json

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

class Tarifa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100))
    tipo = db.Column(db.String(50))
    multiplicador = db.Column(db.Float, default=0)
    fecha_inicio = db.Column(db.Date)
    fecha_fin = db.Column(db.Date)
    posada_id = db.Column(db.Integer, db.ForeignKey('posada.id'))

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
    entrada = datetime.strptime(request.args.get('entrada'), '%Y-%m-%d').date()
    salida = datetime.strptime(request.args.get('salida'), '%Y-%m-%d').date()
    reservas = Reserva.query.filter(
        Reserva.posada_id == posada_id,
        Reserva.estado.in_(['confirmada', 'pago_reportado']),
        Reserva.fecha_entrada < salida,
        Reserva.fecha_salida > entrada
    ).all()
    ocupadas = [r.habitacion_id for r in reservas]
    disponibles = Habitacion.query.filter(
        Habitacion.posada_id == posada_id,
        Habitacion.estado == 'disponible',
        ~Habitacion.id.in_(ocupadas) if ocupadas else True
    ).all()
    dias = max((salida - entrada).days, 1)
    resultado = []
    for h in disponibles:
        total = h.precio_base * dias
        fecha = entrada
        while fecha < salida:
            tarifa = Tarifa.query.filter(
                Tarifa.posada_id == posada_id,
                Tarifa.fecha_inicio <= fecha,
                Tarifa.fecha_fin >= fecha
            ).first()
            if tarifa:
                total += tarifa.multiplicador
            fecha += timedelta(days=1)
        resultado.append({
            'id': h.id, 'nombre': h.nombre, 'tipo': h.tipo,
            'capacidad': h.capacidad, 'precio_total': round(total, 2),
            'precio_por_noche': round(total/dias, 2), 'descripcion': h.descripcion,
            'servicios': json.loads(h.servicios) if h.servicios else [],
            'imagen': h.imagen, 'camas': h.camas
        })
    return jsonify(resultado)

@app.route('/api/reservas', methods=['POST'])
def crear_reserva():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()
    
    entrada = datetime.strptime(data['fecha_entrada'], '%Y-%m-%d').date()
    salida = datetime.strptime(data['fecha_salida'], '%Y-%m-%d').date()
    dias = (salida - entrada).days
    hab = db.session.get(Habitacion, int(data['habitacion_id']))
    if not hab:
        return jsonify({'error': 'Habitacion no encontrada'}), 404
    
    total = hab.precio_base * dias
    fecha = entrada
    while fecha < salida:
        tarifa = Tarifa.query.filter(
            Tarifa.posada_id == hab.posada_id,
            Tarifa.fecha_inicio <= fecha,
            Tarifa.fecha_fin >= fecha
        ).first()
        if tarifa:
            total += tarifa.multiplicador
        fecha += timedelta(days=1)
    
    comprobante_filename = None
    if 'comprobante' in request.files:
        file = request.files['comprobante']
        if file.filename:
            filename = secure_filename(file.filename)
            filename = f"pago_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            comprobante_filename = filename
    
    reserva = Reserva(
        cliente_nombre=data.get('cliente_nombre', ''),
        cliente_cedula=data.get('cliente_cedula', ''),
        cliente_telefono=data.get('cliente_telefono', ''),
        cliente_email=data.get('cliente_email', ''),
        fecha_entrada=entrada, fecha_salida=salida,
        adultos=int(data.get('adultos', 1)), ninos=int(data.get('ninos', 0)),
        total=round(total, 2), habitacion_id=hab.id, posada_id=hab.posada_id,
        metodo_pago=data.get('metodo_pago', ''),
        comprobante=comprobante_filename,
        datos_huespedes=data.get('datos_huespedes', '[]'),
        estado='pago_reportado'
    )
    db.session.add(reserva)
    db.session.commit()
    return jsonify({'message': 'Reserva creada', 'reserva_id': reserva.id, 'total': round(total, 2)})

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
    mes = int(request.args.get('mes', datetime.now().month))
    año = int(request.args.get('año', datetime.now().year))
    inicio = datetime(año, mes, 1).date()
    if mes == 12:
        fin = datetime(año + 1, 1, 1).date() - timedelta(days=1)
    else:
        fin = datetime(año, mes + 1, 1).date() - timedelta(days=1)
    total_dias = fin.day
    primer_dia_semana = (inicio.weekday() + 1) % 7
    reservas = Reserva.query.filter(
        Reserva.posada_id == current_user.posada_id,
        Reserva.estado.in_(['confirmada', 'pago_reportado']),
        Reserva.fecha_entrada <= fin,
        Reserva.fecha_salida >= inicio
    ).all()
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
        'mes': mes, 'año': año,
        'reservas': reservas_por_hab,
        'habitaciones': [{'id': h.id, 'nombre': h.nombre, 'tipo': h.tipo} for h in habitaciones]
    })

@app.route('/api/reservas-pendientes')
@login_required
def reservas_pendientes():
    reservas = Reserva.query.filter_by(
        posada_id=current_user.posada_id, estado='pago_reportado'
    ).order_by(Reserva.fecha_reserva.desc()).all()
    return jsonify([{
        'id': r.id, 'cliente_nombre': r.cliente_nombre,
        'cliente_telefono': r.cliente_telefono,
        'cliente_email': r.cliente_email,
        'fecha_entrada': str(r.fecha_entrada),
        'fecha_salida': str(r.fecha_salida),
        'total': r.total, 'metodo_pago': r.metodo_pago,
        'comprobante': r.comprobante,
        'datos_huespedes': r.datos_huespedes,
        'fecha_reserva': r.fecha_reserva.strftime('%d/%m/%Y %H:%M')
    } for r in reservas])

@app.route('/api/validar-pago/<int:reserva_id>', methods=['POST'])
@login_required
def validar_pago(reserva_id):
    data = request.json
    reserva = db.session.get(Reserva, reserva_id)
    if reserva and reserva.posada_id == current_user.posada_id:
        reserva.estado = data.get('accion', 'confirmada')
        db.session.commit()
        return jsonify({'message': 'Actualizado'})
    return jsonify({'error': 'No encontrada'}), 404

with app.app_context():
    db.create_all()
    if not Usuario.query.filter_by(username='admin').first():
        posada = Posada(nombre='Demo-Posadas', direccion='Sistema de gestión de prueba')
        db.session.add(posada)
        db.session.commit()
        admin = Usuario(username='admin', password_hash=generate_password_hash('admin123'),
                        rol='admin', posada_id=posada.id)
        db.session.add(admin)
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

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True, port=5000)