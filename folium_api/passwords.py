import secrets


TEMPORARY_PASSWORD_WORDS = (
    "sol", "mar", "luna", "rio", "flor", "nube", "lluvia", "viento",
    "fuego", "tierra", "aire", "lago", "pino", "roble", "hoja", "rama",
    "pasto", "campo", "monte", "valle", "playa", "arena", "ola", "isla",
    "cielo", "astro", "noche", "dia", "luz", "sombra", "hielo", "nieve",
    "rayo", "trueno", "brisa", "agua", "roca", "piedra", "barro", "selva",
    "bosque", "planta", "fruto", "raiz", "grano", "brote", "huerta", "jardin",
    "gato", "perro", "raton", "pato", "vaca", "toro", "burro", "mula",
    "oveja", "cabra", "cerdo", "pollo", "gallo", "loro", "mono", "oso",
    "leon", "tigre", "cebra", "jirafa", "panda", "koala", "foca", "lobo",
    "zorro", "conejo", "liebre", "grillo", "abeja", "mosca", "pulpo", "pez",
    "sapo", "rana", "trucha", "carpa", "fideo", "delfin", "marino", "equino",
    "potro", "yegua", "ganso", "cisne", "buho", "paloma", "puma", "pavo",
    "pan", "arroz", "papa", "pera", "uva", "mango", "coco", "limon",
    "fresa", "mora", "miel", "leche", "cafe", "mate", "jugo", "sopa",
    "sal", "masa", "queso", "flan", "torta", "pizza", "pasta", "huevo",
    "atun", "carne", "ajo", "maiz", "trigo", "avena", "nuez", "oliva",
    "yema", "dulce", "salsa", "melon", "sandia", "kiwi", "higo", "yogur",
    "taco", "tarta", "crema", "caldo", "pesto", "frijol", "poroto", "fruta",
    "casa", "mesa", "cama", "sofa", "silla", "taza", "vaso", "plato",
    "olla", "caja", "bolsa", "tela", "lana", "seda", "hilo", "boton",
    "ropa", "gorra", "bota", "zapato", "mano", "dedo", "ojo", "boca",
    "pelo", "cara", "pie", "brazo", "piel", "hueso", "diente", "oreja",
    "nariz", "libro", "papel", "lapiz", "goma", "regla", "mapa", "llave",
    "puerta", "techo", "patio", "foco", "radio", "foto", "cine", "nota",
    "tren", "auto", "bici", "moto", "barco", "vela", "reloj", "pila",
    "cable", "peine", "jabon", "toalla", "manta", "banco", "carro", "rueda",
    "salta", "canta", "corre", "juega", "mira", "rie", "ama", "siente",
    "vive", "come", "bebe", "anda", "pasa", "trae", "toca", "sonrie",
    "duerme", "baila", "nada", "monta", "lee", "firma", "camina", "vuela",
    "abraza", "calma", "paz", "suerte", "ayuda", "amigo", "amiga", "madre",
    "padre", "hijo", "hija", "joven", "gente", "hogar", "barrio", "limpio",
    "claro", "suave", "rapido", "lento", "nuevo", "viejo", "alto", "bajo",
    "frio", "tibio", "sano", "feliz", "justo", "libre", "fuerte", "listo",
    "bueno", "malo", "corto", "ancho", "curvo", "recto", "verde", "rojo",
    "azul", "rosa", "gris", "negro", "blanco", "morado", "dorado", "plata",
    "norte", "sur", "este", "oeste", "uno", "dos", "tres", "cuatro",
    "cinco", "seis", "siete", "ocho", "nueve", "diez", "hoy", "ayer",
    "manana", "tarde", "pronto", "lejos", "cerca", "arriba", "abajo", "dentro",
    "fuera", "junto", "solo", "broma", "juego", "risa", "canto", "baile",
    "ruido", "quieto", "calor", "idea", "salud", "amable", "ameno", "calido",
    "rico", "fresco", "tierno", "simple", "amplio", "bravo", "manso", "firme",
)


def generate_temporary_password():
    words = secrets.SystemRandom().sample(TEMPORARY_PASSWORD_WORDS, 5)
    digits = f"{secrets.randbelow(10_000):04d}"
    return "-".join((*words, digits))
