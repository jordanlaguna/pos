"""División territorial de Hacienda: la nota 14 del anexo, `Codificacionubicacion_V4.4`.

**Generado** por `docs/hacienda/costa-rica/generar_ubicaciones.py` a partir del Excel oficial. No se edita a mano: se regenera.

Las llaves de `DISTRICTS` son «provincia-cantón»: `"1-01"`.
"""

from typing import Final

PROVINCES: Final[dict[str, str]] = {
    "1": "San José",
    "2": "Alajuela",
    "3": "Cartago",
    "4": "Heredia",
    "5": "Guanacaste",
    "6": "Puntarenas",
    "7": "Limón"
}

CANTONS: Final[dict[str, dict[str, str]]] = {
    "1": {
        "01": "San José",
        "02": "Escazú",
        "03": "Desamparados",
        "04": "Puriscal",
        "05": "Tarrazú",
        "06": "Aserrí",
        "07": "Mora",
        "08": "Goicoechea",
        "09": "Santa Ana",
        "10": "Alajuelita",
        "11": "Vázquez de Coronado",
        "12": "Acosta",
        "13": "Tibás",
        "14": "Moravia",
        "15": "Montes de Oca",
        "16": "Turrubares",
        "17": "Dota",
        "18": "Curridabat",
        "19": "Pérez Zeledón",
        "20": "León Cortés Castro"
    },
    "2": {
        "01": "Alajuela",
        "02": "San Ramón",
        "03": "Grecia",
        "04": "San Mateo",
        "05": "Atenas",
        "06": "Naranjo",
        "07": "Palmares",
        "08": "Poás",
        "09": "Orotina",
        "10": "San Carlos",
        "11": "Zarcero",
        "12": "Sarchí",
        "13": "Upala",
        "14": "Los Chiles",
        "15": "Guatuso",
        "16": "Río Cuarto"
    },
    "3": {
        "01": "Cartago",
        "02": "Paraíso",
        "03": "La Unión",
        "04": "Jiménez",
        "05": "Turrialba",
        "06": "Alvarado",
        "07": "Oreamuno",
        "08": "El Guarco"
    },
    "4": {
        "01": "Heredia",
        "02": "Barva",
        "03": "Santo Domingo",
        "04": "Santa Bárbara",
        "05": "San Rafael",
        "06": "San Isidro",
        "07": "Belén",
        "08": "Flores",
        "09": "San Pablo",
        "10": "Sarapiquí"
    },
    "5": {
        "01": "Liberia",
        "02": "Nicoya",
        "03": "Santa Cruz",
        "04": "Bagaces",
        "05": "Carrillo",
        "06": "Cañas",
        "07": "Abangares",
        "08": "Tilarán",
        "09": "Nandayure",
        "10": "La Cruz",
        "11": "Hojancha"
    },
    "6": {
        "01": "Puntarenas",
        "02": "Esparza",
        "03": "Buenos Aires",
        "04": "Montes de Oro",
        "05": "Osa",
        "06": "Quepos",
        "07": "Golfito",
        "08": "Coto Brus",
        "09": "Parrita",
        "10": "Corredores",
        "11": "Garabito",
        "12": "Monte Verde",
        "13": "Puerto Jimenez"
    },
    "7": {
        "01": "Limón",
        "02": "Pococí",
        "03": "Siquirres",
        "04": "Talamanca",
        "05": "Matina",
        "06": "Guácimo"
    }
}

DISTRICTS: Final[dict[str, dict[str, str]]] = {
    "1-01": {
        "01": "Carmen",
        "02": "Merced",
        "03": "Hospital",
        "04": "Catedral",
        "05": "Zapote",
        "06": "San Francisco de Dos Ríos",
        "07": "Uruca",
        "08": "Mata Redonda",
        "09": "Pavas",
        "10": "Hatillo",
        "11": "San Sebástian"
    },
    "1-02": {
        "01": "Escazú",
        "02": "San Antonio",
        "03": "San Rafael"
    },
    "1-03": {
        "01": "Desamparados",
        "02": "San Miguel",
        "03": "San Juan de Dios",
        "04": "San Rafael Arriba",
        "05": "San Antonio",
        "06": "Frailes",
        "07": "Patarrá",
        "08": "San Cristóbal",
        "09": "Rosario",
        "10": "Damas",
        "11": "San Rafael Abajo",
        "12": "Gravilias",
        "13": "Los Guido"
    },
    "1-04": {
        "01": "Santiago",
        "02": "Mercedes Sur",
        "03": "Barbacoas",
        "04": "Grifo Alto",
        "05": "San Rafael",
        "06": "Candelarita",
        "07": "Desamparaditos",
        "08": "San Antonio",
        "09": "Chires"
    },
    "1-05": {
        "01": "San Marcos",
        "02": "San Lorenzo",
        "03": "San Carlos"
    },
    "1-06": {
        "01": "Aserrí",
        "02": "Tarbaca",
        "03": "Vuelta de Jorco",
        "04": "San Gabriel",
        "05": "Legua",
        "06": "Monterrey",
        "07": "Salitrillos"
    },
    "1-07": {
        "01": "Colón",
        "02": "Guayabo",
        "03": "Tabarcia",
        "04": "Piedras Negras",
        "05": "Picagres",
        "06": "Jaris",
        "07": "Quitirrisí"
    },
    "1-08": {
        "01": "Guadalupe",
        "02": "San Francisco",
        "03": "Calle Blancos",
        "04": "Mata de Plátano",
        "05": "Ipís",
        "06": "Rancho Redondo",
        "07": "Purral"
    },
    "1-09": {
        "01": "Santa Ana",
        "02": "Salitral",
        "03": "Pozos",
        "04": "Uruca",
        "05": "Piedades",
        "06": "Brasil"
    },
    "1-10": {
        "01": "Alajuelita",
        "02": "San Josecito",
        "03": "San Antonio",
        "04": "Concepción",
        "05": "San Felipe"
    },
    "1-11": {
        "01": "San Isidro",
        "02": "San Rafael",
        "03": "Dulce Nombre de Jesús",
        "04": "Patalillo",
        "05": "Cascajal"
    },
    "1-12": {
        "01": "San Ignacio",
        "02": "Guaitil",
        "03": "Palmichal",
        "04": "Cangrejal",
        "05": "Sabanillas"
    },
    "1-13": {
        "01": "San Juan",
        "02": "Cinco Esquinas",
        "03": "Anselmo Llorente",
        "04": "León XIII",
        "05": "Colima"
    },
    "1-14": {
        "01": "San Vicente",
        "02": "San Jerónimo",
        "03": "La Trinidad"
    },
    "1-15": {
        "01": "San Pedro",
        "02": "Sabanilla",
        "03": "Mercedes",
        "04": "San Rafael"
    },
    "1-16": {
        "01": "San Pablo",
        "02": "San Pedro",
        "03": "San Juan de Mata",
        "04": "San Luis",
        "05": "Carara"
    },
    "1-17": {
        "01": "Santa María",
        "02": "Jardín",
        "03": "Copey"
    },
    "1-18": {
        "01": "Curridabat",
        "02": "Granadilla",
        "03": "Sánchez",
        "04": "Tirrases"
    },
    "1-19": {
        "01": "San Isidro de El General",
        "02": "El General",
        "03": "Daniel Flores",
        "04": "Rivas",
        "05": "San Pedro",
        "06": "Platanares",
        "07": "Pejibaye",
        "08": "Cajón",
        "09": "Barú",
        "10": "Río Nuevo",
        "11": "Páramo",
        "12": "La Amistad"
    },
    "1-20": {
        "01": "San Pablo",
        "02": "San Andrés",
        "03": "Llano Bonito",
        "04": "San Isidro",
        "05": "Santa Cruz",
        "06": "San Antonio"
    },
    "2-01": {
        "01": "Alajuela",
        "02": "San José",
        "03": "Carrizal",
        "04": "San Antonio",
        "05": "Guácima",
        "06": "San Isidro",
        "07": "Sabanilla",
        "08": "San Rafael",
        "09": "Río Segundo",
        "10": "Desamparados",
        "11": "Turrúcares",
        "12": "Tambor",
        "13": "Garita",
        "14": "Sarapiquí"
    },
    "2-02": {
        "01": "San Ramón",
        "02": "Santiago",
        "03": "San Juan",
        "04": "Piedades Norte",
        "05": "Piedades Sur",
        "06": "San Rafael",
        "07": "San Isidro",
        "08": "Ángeles",
        "09": "Alfaro",
        "10": "Volio",
        "11": "Concepción",
        "12": "Zapotal",
        "13": "Peñas Blancas",
        "14": "San Lorenzo"
    },
    "2-03": {
        "01": "Grecia",
        "02": "San Isidro",
        "03": "San José",
        "04": "San Roque",
        "05": "Tacares",
        "06": "Puente de Piedra",
        "07": "Bolívar"
    },
    "2-04": {
        "01": "San Mateo",
        "02": "Desmonte",
        "03": "Jesús María",
        "04": "Labrador"
    },
    "2-05": {
        "01": "Atenas",
        "02": "Jesús",
        "03": "Mercedes",
        "04": "San Isidro",
        "05": "Concepción",
        "06": "San José",
        "07": "Santa Eulalia",
        "08": "Escobal"
    },
    "2-06": {
        "01": "Naranjo",
        "02": "San Miguel",
        "03": "San José",
        "04": "Cirrí Sur",
        "05": "San Jerónimo",
        "06": "San Juan",
        "07": "Rosario",
        "08": "Palmitos"
    },
    "2-07": {
        "01": "Palmares",
        "02": "Zaragoza",
        "03": "Buenos Aires",
        "04": "Santiago",
        "05": "Candelaria",
        "06": "Esquipulas",
        "07": "Granja"
    },
    "2-08": {
        "01": "San Pedro",
        "02": "San Juan",
        "03": "San Rafael",
        "04": "Carrillos",
        "05": "Sabana Redonda"
    },
    "2-09": {
        "01": "Orotina",
        "02": "El Mastate",
        "03": "Hacienda Vieja",
        "04": "Coyolar",
        "05": "Ceiba"
    },
    "2-10": {
        "01": "Quesada",
        "02": "Florencia",
        "03": "Buenavista",
        "04": "Aguas Zarcas",
        "05": "Venecia",
        "06": "Pital",
        "07": "Fortuna",
        "08": "Tigra",
        "09": "Palmera",
        "10": "Venado",
        "11": "Cutris",
        "12": "Monterrey",
        "13": "Pocosol"
    },
    "2-11": {
        "01": "Zarcero",
        "02": "Laguna",
        "03": "Tapezco",
        "04": "Guadalupe",
        "05": "Palmira",
        "06": "Zapote",
        "07": "Brisas"
    },
    "2-12": {
        "01": "Sarchí Norte",
        "02": "Sarchí Sur",
        "03": "Toro Amarillo",
        "04": "San Pedro",
        "05": "Rodríguez"
    },
    "2-13": {
        "01": "Upala",
        "02": "Aguas Claras",
        "03": "San José o Pizote",
        "04": "Bijagua",
        "05": "Delicias",
        "06": "Dos Ríos",
        "07": "Yolillal",
        "08": "Canalete"
    },
    "2-14": {
        "01": "Los Chiles",
        "02": "Caño Negro",
        "03": "El Amparo",
        "04": "San Jorge"
    },
    "2-15": {
        "01": "San Rafael",
        "02": "Buenavista",
        "03": "Cote",
        "04": "Katira"
    },
    "2-16": {
        "01": "Río Cuarto",
        "02": "Santa Rita",
        "03": "Santa Isabel"
    },
    "3-01": {
        "01": "Oriental",
        "02": "Occidental",
        "03": "Carmen",
        "04": "San Nicolás",
        "05": "Aguacaliente o San Francisco",
        "06": "Guadalupe o Arenilla",
        "07": "Corralillo",
        "08": "Tierra Blanca",
        "09": "Dulce Nombre",
        "10": "Llano Grande",
        "11": "Quebradilla"
    },
    "3-02": {
        "01": "Paraíso",
        "02": "Santiago",
        "03": "Orosi",
        "04": "Cachí",
        "05": "Llanos de Santa Lucía",
        "06": "Birrisito"
    },
    "3-03": {
        "01": "Tres Ríos",
        "02": "San Diego",
        "03": "San Juan",
        "04": "San Rafael",
        "05": "Concepción",
        "06": "Dulce Nombre",
        "07": "San Ramón",
        "08": "Río Azul"
    },
    "3-04": {
        "01": "Juan Viñas",
        "02": "Tucurrique",
        "03": "Pejibaye",
        "04": "La Victoria"
    },
    "3-05": {
        "01": "Turrialba",
        "02": "La Suiza",
        "03": "Peralta",
        "04": "Santa Cruz",
        "05": "Santa Teresita",
        "06": "Pavones",
        "07": "Tuis",
        "08": "Tayutic",
        "09": "Santa Rosa",
        "10": "Tres Equis",
        "11": "La Isabel",
        "12": "Chirripó"
    },
    "3-06": {
        "01": "Pacayas",
        "02": "Cervantes",
        "03": "Capellades"
    },
    "3-07": {
        "01": "San Rafael",
        "02": "Cot",
        "03": "Potrero Cerrado",
        "04": "Cipreses",
        "05": "Santa Rosa"
    },
    "3-08": {
        "01": "El Tejar",
        "02": "San Isidro",
        "03": "Tobosi",
        "04": "Patio de Agua"
    },
    "4-01": {
        "01": "Heredia",
        "02": "Mercedes",
        "03": "San Francisco",
        "04": "Ulloa",
        "05": "Vara Blanca"
    },
    "4-02": {
        "01": "Barva",
        "02": "San Pedro",
        "03": "San Pablo",
        "04": "San Roque",
        "05": "Santa Lucía",
        "06": "San José de la Montaña",
        "07": "Puente Salas"
    },
    "4-03": {
        "01": "Santo Domingo",
        "02": "San Vicente",
        "03": "San Miguel",
        "04": "Paracito",
        "05": "Santo Tomás",
        "06": "Santa Rosa",
        "07": "Tures",
        "08": "Pará"
    },
    "4-04": {
        "01": "Santa Bárbara",
        "02": "San Pedro",
        "03": "San Juan",
        "04": "Jesús",
        "05": "Santo Domingo",
        "06": "Purabá"
    },
    "4-05": {
        "01": "San Rafael",
        "02": "San Josecito",
        "03": "Santiago",
        "04": "Ángeles",
        "05": "Concepción"
    },
    "4-06": {
        "01": "San Isidro",
        "02": "San José",
        "03": "Concepción",
        "04": "San Francisco"
    },
    "4-07": {
        "01": "San Antonio",
        "02": "La Ribera",
        "03": "Asunción"
    },
    "4-08": {
        "01": "San Joaquín",
        "02": "Barrantes",
        "03": "Llorente"
    },
    "4-09": {
        "01": "San Pablo",
        "02": "Rincón de Sabanilla"
    },
    "4-10": {
        "01": "Puerto Viejo",
        "02": "La Virgen",
        "03": "Horquetas",
        "04": "Llanuras del Gaspar",
        "05": "Cureña"
    },
    "5-01": {
        "01": "Liberia",
        "02": "Cañas Dulces",
        "03": "Mayorga",
        "04": "Nacascolo",
        "05": "Curubandé"
    },
    "5-02": {
        "01": "Nicoya",
        "02": "Mansión",
        "03": "San Antonio",
        "04": "Quebrada Honda",
        "05": "Sámara",
        "06": "Nosara",
        "07": "Belén de Nosarita"
    },
    "5-03": {
        "01": "Santa Cruz",
        "02": "Bolsón",
        "03": "Veintisiete de Abril",
        "04": "Tempate",
        "05": "Cartagena",
        "06": "Cuajiniquil",
        "07": "Diriá",
        "08": "Cabo Velas",
        "09": "Tamarindo"
    },
    "5-04": {
        "01": "Bagaces",
        "02": "Fortuna",
        "03": "Mogote",
        "04": "Río Naranjo"
    },
    "5-05": {
        "01": "Filadelfia",
        "02": "Palmira",
        "03": "Sardinal",
        "04": "Belén"
    },
    "5-06": {
        "01": "Cañas",
        "02": "Palmira",
        "03": "San Miguel",
        "04": "Bebedero",
        "05": "Porozal"
    },
    "5-07": {
        "01": "Las Juntas",
        "02": "Sierra",
        "03": "San Juan",
        "04": "Colorado"
    },
    "5-08": {
        "01": "Tilarán",
        "02": "Quebrada Grande",
        "03": "Tronadora",
        "04": "Santa Rosa",
        "05": "Líbano",
        "06": "Tierras Morenas",
        "07": "Arenal",
        "08": "CABECERAS (hasta ser publicado en el diario oficial La Gaceta)"
    },
    "5-09": {
        "01": "Carmona",
        "02": "Santa Rita",
        "03": "Zapotal",
        "04": "San Pablo",
        "05": "Porvenir",
        "06": "Bejuco"
    },
    "5-10": {
        "01": "La Cruz",
        "02": "Santa Cecilia",
        "03": "La Garita",
        "04": "Santa Elena"
    },
    "5-11": {
        "01": "Hojancha",
        "02": "Monte Romo",
        "03": "Puerto Carrillo",
        "04": "Huacas",
        "05": "Matambú"
    },
    "6-01": {
        "01": "Puntarenas",
        "02": "Pitahaya",
        "03": "Chomes",
        "04": "Lepanto",
        "05": "Paquera",
        "06": "Manzanillo",
        "07": "Guacimal",
        "08": "Barranca",
        "10": "Isla del Coco",
        "11": "Cóbano",
        "12": "Chacarita",
        "13": "Chira",
        "14": "Acapulco",
        "15": "El Roble",
        "16": "Arancibia"
    },
    "6-02": {
        "01": "Espíritu Santo",
        "02": "San Juan Grande",
        "03": "Macacona",
        "04": "San Rafael",
        "05": "San Jerónimo",
        "06": "Caldera"
    },
    "6-03": {
        "01": "Buenos Aires",
        "02": "Volcán",
        "03": "Potrero Grande",
        "04": "Boruca",
        "05": "Pilas",
        "06": "Colinas",
        "07": "Chánguena",
        "08": "Biolley",
        "09": "Brunka"
    },
    "6-04": {
        "01": "Miramar",
        "02": "La Unión",
        "03": "San Isidro"
    },
    "6-05": {
        "01": "Puerto Cortés",
        "02": "Palmar",
        "03": "Sierpe",
        "04": "Bahía Ballena",
        "05": "Piedras Blancas",
        "06": "Bahía Drake"
    },
    "6-06": {
        "01": "Quepos",
        "02": "Savegre",
        "03": "Naranjito"
    },
    "6-07": {
        "01": "Golfito",
        "03": "Guaycará",
        "04": "Pavón"
    },
    "6-08": {
        "01": "San Vito",
        "02": "Sabalito",
        "03": "Aguabuena",
        "04": "Limoncito",
        "05": "Pittier",
        "06": "Gutiérrez Braun"
    },
    "6-09": {
        "01": "Parrita"
    },
    "6-10": {
        "01": "Corredor",
        "02": "La Cuesta",
        "03": "Canoas",
        "04": "Laurel"
    },
    "6-11": {
        "01": "Jacó",
        "02": "Tárcoles",
        "03": "Lagunillas"
    },
    "6-12": {
        "01": "Monte Verde"
    },
    "6-13": {
        "01": "Puerto Jimenez"
    },
    "7-01": {
        "01": "Limón",
        "02": "Valle La Estrella",
        "03": "Río Blanco",
        "04": "Matama"
    },
    "7-02": {
        "01": "Guápiles",
        "02": "Jiménez",
        "03": "Rita",
        "04": "Roxana",
        "05": "Cariari",
        "06": "Colorado",
        "07": "La Colonia"
    },
    "7-03": {
        "01": "Siquirres",
        "02": "Pacuarito",
        "03": "Florida",
        "04": "Germania",
        "05": "El Cairo",
        "06": "Alegría",
        "07": "Reventazón"
    },
    "7-04": {
        "01": "Bratsi",
        "02": "Sixaola",
        "03": "Cahuita",
        "04": "Telire"
    },
    "7-05": {
        "01": "Matina",
        "02": "Batán",
        "03": "Carrandi"
    },
    "7-06": {
        "01": "Guácimo",
        "02": "Mercedes",
        "03": "Pocora",
        "04": "Río Jiménez",
        "05": "Duacarí"
    }
}
