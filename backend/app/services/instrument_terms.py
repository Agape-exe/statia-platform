"""Vocabulario de búsqueda local. Los términos afines solo seleccionan evidencia."""

# Cada grupo distingue lo que activa la búsqueda de la evidencia relacionada
# que se puede recuperar. Una coincidencia no afirma equivalencia metodológica.
VOCABULARY = {
    "devices": (
        "dispositivo digital|dispositivos digitales|dispositivos electronicos|equipo electronico|equipos electronicos|"
        "aparatos electronicos|digital device|digital devices|electronic device|electronic devices",
        "device|devices|dispositivo|dispositivos|smartphone|tablet|laptop|desktop computer|telefono inteligente|computadora portatil",
    ),
    "connectivity": (
        "internet|conectividad|conexion a internet|banda ancha|acceso a la red|uso de la red|connectivity|broadband",
        "internet|wifi|wi fi|broadband|online|en linea|network access|web access|conectividad|banda ancha",
    ),
    "digital_skills": (
        "competencias digitales|competencia digital|habilidades digitales|destrezas digitales|habilidades tecnologicas|"
        "alfabetizacion digital|digital skills|digital literacy|digital competence|computer skills|online skills",
        "competencias digitales|habilidades digitales|digital skills|digital literacy|digital competence|"
        "computer skills|online skills|word processing|spreadsheet management|ict skills|basic computer|skills in the following",
    ),
    "learning": (
        "aprendizaje|rendimiento academico|desempeno academico|academic performance|learning outcomes|school achievement",
        "aprendizaje|learning|academic performance|school achievement|grades|exam results|calificaciones|rendimiento academico",
    ),
    "attendance": (
        "asistencia escolar|ausentismo|faltas a clase|school attendance|absenteeism|missed classes",
        "asistencia escolar|school attendance|absenteeism|missed classes|class attendance|ausentismo|faltas a clase",
    ),
    "wellbeing": (
        "bienestar|satisfaccion vital|calidad de vida|wellbeing|well being|life satisfaction|quality of life",
        "bienestar|wellbeing|well being|life satisfaction|quality of life|satisfaccion vital|calidad de vida",
    ),
    "social_support": (
        "apoyo social|red de apoyo|ayuda de otras personas|social support|support network",
        "apoyo social|red de apoyo|social support|support network|someone to turn to|help from family|help from friends",
    ),
    "work": (
        "empleo|situacion laboral|condiciones de trabajo|employment|working conditions|job status",
        "empleo|situacion laboral|condiciones de trabajo|employment|working conditions|job status|work hours|hours worked",
    ),
    "income": (
        "ingresos|sueldo|salario|remuneracion|income|earnings|salary|wages",
        "ingresos|sueldo|salario|remuneracion|income|earnings|salary|wages",
    ),
    "transport": (
        "transporte|movilidad urbana|desplazamiento|commute|transportation|public transit",
        "transporte|desplazamiento|commute|transportation|public transit|travel time|bus service",
    ),
    "healthcare": (
        "atencion sanitaria|atencion medica|servicios de salud|health care|healthcare|medical care|health services",
        "atencion sanitaria|servicios de salud|health care|healthcare|medical care|health services|doctor visits",
    ),
    "sleep": (
        "sueno|dormir|descanso nocturno|sleep|sleeping|night rest",
        "sueno|dormir|descanso nocturno|sleep|sleeping|night rest|bedtime|daytime sleepiness",
    ),
    "food": (
        "seguridad alimentaria|inseguridad alimentaria|acceso a alimentos|food security|food insecurity|food access",
        "seguridad alimentaria|inseguridad alimentaria|acceso a alimentos|food security|food insecurity|food access|enough food",
    ),
    "language": (
        "dominio del idioma|competencia linguistica|habilidades linguisticas|language proficiency|language skills",
        "dominio del idioma|competencia linguistica|language proficiency|language skills|speaking fluency|reading fluency",
    ),
}


def contains_phrase(text, alternatives):
    return any(f" {phrase} " in text for phrase in alternatives.split("|"))


def requested_topics(word_text):
    return {topic: evidence for topic, (request, evidence) in VOCABULARY.items() if contains_phrase(word_text, request)}
