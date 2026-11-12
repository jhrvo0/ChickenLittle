"""Diagramas técnicos de apoio, derivados das fontes; não gera fotos nem UI."""
from pathlib import Path
from html import escape
import json

OUT = Path('docs/academico/checkpoint_2026-11-12/figuras')


class Drawing:
    def __init__(self, width, height, title):
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
                      f'<title>{escape(title)}</title>',
                      '<defs><marker id="arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8" fill="#374151"/></marker></defs>',
                      f'<rect width="{width}" height="{height}" fill="white"/>']

    def text(self, x, y, value, size=24, weight=400, color='#172033', anchor='start'):
        self.parts.append(f'<text x="{x}" y="{y}" font-family="Arial, sans-serif" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}">{escape(value)}</text>')

    def rect(self, x, y, w, h, fill='#f5f7fa', stroke='#c6ccd6', dashed=False):
        dash = ' stroke-dasharray="10 7"' if dashed else ''
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="2"{dash}/>')

    def path(self, points, color='#374151', arrow=False, dashed=False, width=3):
        coords = ' '.join(f'{x},{y}' for x, y in points)
        extras = (' marker-end="url(#arrow)"' if arrow else '') + (' stroke-dasharray="11 8"' if dashed else '')
        self.parts.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round"{extras}/>')

    def node(self, x, y, w, lines, color='#f5f7fa', dashed=False):
        self.rect(x, y, w, 106, fill=color, dashed=dashed)
        for i, line in enumerate(lines):
            self.text(x+w/2, y+33+i*28, line, 22 if i else 24, 700 if i == 0 else 400, anchor='middle')

    def dot(self, x, y):
        self.parts.append(f'<circle cx="{x}" cy="{y}" r="7" fill="#172033"/>')

    def ground(self, x, y):
        self.path([(x,y),(x,y+14)])
        for dy, half in [(14,19),(22,12),(30,6)]:
            self.path([(x-half,y+dy),(x+half,y+dy)],width=2)

    def save(self, name):
        (OUT/name).write_text('\n'.join(self.parts+['</svg>']),encoding='utf-8')


net = json.loads(Path('hardware/netlist/motionpet_atual_sem_lcd.json').read_text())
assert net['firmware_pins'] == {'PIN_HCSR04_TRIG':5,'PIN_HCSR04_ECHO':34,'PIN_TCRT5000_DO':35}
assert [r['ohms'] for r in net['resistors']] == [1000,1000,300]

d = Drawing(1400, 1010, 'Figura 1 Circuito vigente sem LCD')
d.text(55,60,'Figura 1  Circuito vigente sem LCD',38,700)
d.text(55,99,'Derivado da netlist revisão 5 • montagem relatada em 10/11/2026 • não é fotografia',23)
d.rect(80,190,320,585,'#edf4fb','#406a98')
d.text(110,239,'ESP32 DevKit',31,700); d.text(110,273,'38 pinos • P1',25)
d.rect(1000,190,330,280,'#f5f7fa')
d.text(1030,230,'HC-SR04',30,700)
d.rect(1000,575,330,230,'#f5f7fa')
d.text(1030,618,'TCRT5000',30,700)

d.text(110,327,'GPIO5  /  P1:10A',24); d.text(1020,327,'TRIG',24)
d.path([(400,320),(1000,320)],'#356ea5',True)
d.text(1020,267,'VCC 5 V',24); d.path([(900,260),(1000,260)],'#bd4b3d')
d.text(792,250,'5 V • trilho + P1',23,color='#9e382d')
d.text(1020,397,'ECHO',24)
d.path([(1000,390),(825,390)])
d.rect(745,376,80,28,'white','#374151'); d.text(785,360,'R1 1 kΩ',24,anchor='middle')
d.path([(745,390),(660,390)]); d.dot(660,390)
d.path([(660,390),(560,390),(560,470),(400,470)],'#356ea5',True)
d.text(110,478,'GPIO34 / P1:15J',24)
d.path([(660,390),(660,430)])
d.rect(646,430,28,60,'white','#374151'); d.text(705,466,'R2 1 kΩ',24)
d.path([(660,490),(660,520)])
d.rect(646,520,28,60,'white','#374151'); d.text(705,556,'R3 300 Ω',24)
d.path([(660,580),(660,607)]); d.ground(660,607)
d.text(705,614,'GND comum',23)
d.text(1020,447,'GND',24); d.path([(1000,440),(955,440),(955,480)]); d.ground(955,480)

d.text(110,550,'5 V → trilho + P1',23,color='#9e382d')
d.text(110,589,'3V3 → trilho + P2',23,color='#9e382d')
d.text(110,629,'GND por P1:6J',23)
d.text(110,720,'GPIO35 / P1:14J',24); d.text(1020,717,'DO',24)
d.path([(1000,710),(400,710)],'#356ea5',True)
d.text(1020,658,'VCC 3,3 V',24); d.path([(950,650),(1000,650)],'#bd4b3d')
d.text(798,638,'3V3 • trilho + P2',23,color='#9e382d')
d.text(1020,767,'GND',24); d.path([(1000,760),(955,760),(955,808)]); d.ground(955,808)
d.text(1030,798,'AO sem ligação',22)
d.rect(450,125,490,100,'#fff8e8','#c5a354')
d.text(470,165,'Nó do divisor → GPIO34',26,700)
d.text(470,200,'2,83 V nominal calculado; não medido',23)
d.text(55,866,'P2: R1 8C–12C • R2 12D–16D • R3 16E–20E • 20A → GND',25)
d.text(55,904,'5 V e 3,3 V em trilhos separados; negativos interligados. Sem LCD ou atuador externo.',24)
d.text(55,942,'Fonte: hardware/netlist/motionpet_atual_sem_lcd.json + docs/bench_verified_wiring.md',21)
d.text(55,975,'Conferência estática em 11/11/2026. Sem COM3, simulação elétrica ou nova validação física.',21)
d.save('figura-1-circuito-atual.svg')

d = Drawing(1500, 1260, 'Figura 3 Arquitetura atual do MotionLab')
d.text(40,55,'Figura 3  Arquitetura atual do MotionLab',38,700)
d.text(40,94,'Três estados explícitos: USB existente • MQTT integrado em software • rede da ESP32 pendente',24)
d.rect(25,125,1450,265,'#f5f9fd','#8faecb')
d.text(45,165,'A  USB EXISTENTE',27,700)
d.text(410,165,'Firmware implementado; bancada relatada anteriormente; sem ensaio físico nesta rodada',22)
for x,w,lines in [(45,180,['HC-SR04','+ TCRT5000']), (260,215,['ESP32','FreeRTOS','TinyML sintético']), (515,190,['USB serial','JSON Lines v1']), (745,300,['Backend Python','sessão + MotionEngine']), (1090,360,['Dashboard MotionLab','api/live e api/lab'])]:
    d.node(x,200,w,lines,'white')
for a,b in [(225,260),(475,515),(705,745),(1045,1090)]:
    d.path([(a,253),(b,253)],arrow=True)
d.text(45,347,'DEMO da UI: simulador → serial virtual → mesmo backend. Esse fluxo ao vivo não usa MQTT.',24)

d.rect(25,420,1450,525,'#f8faf7','#94a993')
d.text(45,460,'B  MQTT DE SOFTWARE',27,700)
d.text(450,460,'Fase C: sessões sintéticas persistidas e processadas; stack não reiniciada nesta rodada',22)
for x,w,lines in [(45,250,['Publisher sintético','sessões completas']), (360,240,['Mosquitto','MQTT QoS 1']), (665,300,['Consumidor Python','validação + deduplicação']), (1030,415,['Persistência JSONL','sessões por origem'])]:
    d.node(x,495,w,lines,'white')
for a,b in [(295,360),(600,665),(965,1030)]:
    d.path([(a,548),(b,548)],arrow=True)
d.path([(800,601),(800,640),(485,640),(485,601)],arrow=True)
d.text(815,644,'Recibo de persistência → publisher',22)
d.path([(1238,601),(1238,670),(155,670),(155,740)],arrow=True)
d.text(380,700,'Preparação e treino em lote',22)
d.path([(1420,601),(1420,705),(1090,705),(1090,740)],arrow=True)
d.text(1090,695,'Novas sessões → inferência',20,anchor='middle')
for x,w,lines in [(45,220,['Airflow','4 tarefas em lote']), (335,240,['Experimento','MLflow: rastreio','treino no host']), (650,260,['Publicação explícita','modelo + hashes']), (980,220,['API + worker','modelo publicado']), (1235,210,['Dashboard','proxy api/ml/*'])]:
    d.node(x,740,w,lines,'white')
for a,b in [(265,335),(575,650),(910,980),(1200,1235)]:
    d.path([(a,793),(b,793)],arrow=True)
d.text(45,894,'Verificado agora: HTTP das quatro rotas /api/ml/* • entrada DEMO • treino sintético • físico pendente',23)

d.rect(25,980,1450,195,'#fffaf1','#bb8d3f',True)
d.text(45,1020,'C  ESP32 POR WI-FI / MQTT',27,700)
d.node(45,1040,220,['ESP32','MQTT ausente','no firmware'],'white',True)
d.node(495,1040,285,['Wi-Fi da LAN','implementação','suspensa'],'white',True)
d.node(1040,1040,405,['Broker no notebook','acesso LAN ainda pendente'],'white',True)
d.path([(265,1093),(495,1093)],arrow=True,dashed=True)
d.path([(780,1093),(1040,1093)],arrow=True,dashed=True)
d.text(40,1215,'O broker atual é publicado em 127.0.0.1:1883. Esse endereço não é alcançável pela ESP32 na rede local.',23)
d.text(40,1250,'Fontes: firmware/main/main.cpp • ml/mqtt_ingestion.py • ops/mlops/compose.yaml • evidências Fase C e HTTP',20)
d.save('figura-3-arquitetura.svg')
print('Diagramas SVG gerados a partir das fontes conferidas.')
