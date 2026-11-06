// =====================================================================
//  chasis.scad – Modelo CAD paramétrico del robot móvil ESP32 (diseño propio)
//  Unidades: mm.  Origen: centro del robot sobre el piso. +X = frente.
//
//  Exportar:
//    openscad -o ensamble.png  --imgsize=1600,1200 chasis.scad
//    openscad -D 'PARTE="base_2d"'     -o placa_base.dxf     chasis.scad   (corte láser)
//    openscad -D 'PARTE="superior_2d"' -o placa_superior.dxf chasis.scad
//    openscad -D 'PARTE="soporte_sensores"' -o soporte_sensores.stl chasis.scad (impresión 3D)
//    openscad -D 'PARTE="mastil"'      -o mastil_brujula.stl  chasis.scad
//    openscad -D 'PARTE="soporte_sonar"' -o soporte_sonar.stl chasis.scad
// =====================================================================
PARTE = "ensamble";   // ensamble | base_2d | superior_2d | soporte_sensores | mastil | soporte_sonar

// ------------------------------- parámetros ---------------------------
L = 200;  W = 140;  T = 3;  R = 12;      // placas MDF/acrílico 3 mm
RUEDA_D = 65;  RUEDA_A = 26;             // ruedas TT
EJE_X = 60;                              // posición de ejes (±)
MOTOR = [64, 19, 22.5];                  // motorreductor TT 1:48 (L, ancho, alto)
Z_BASE = RUEDA_D / 2 + 11;               // cara inferior de la placa base
SEP = 45;                                // separadores M3 entre placas
Z_SUP = Z_BASE + T + SEP;                // cara inferior de la placa superior
MASTIL_H = 80;                           // mástil de la brújula (lejos de motores)
$fn = 48;

module placa2d(sup = false) {
  difference() {
    offset(r = R) offset(delta = -R) square([L, W], center = true);
    // agujeros de separadores M3
    for (x = [-85, 0, 85], y = [-58, 58]) translate([x, y]) circle(d = 3.4);
    if (!sup) {
      // fijación de motores (2 tornillos M3 por motor)
      for (sx = [-1, 1], sy = [-1, 1]) translate([sx * EJE_X, sy * 52]) {
        translate([-sx * 18, 0]) circle(d = 3.4);
        translate([-sx * 36, 0]) circle(d = 3.4);
      }
      // paso de cables de motores y sensores inferiores
      for (sx = [-1, 1]) translate([sx * 30, 0]) offset(r = 3) square([8, 30], center = true);
      translate([88, 0]) offset(r = 2) square([10, 40], center = true);       // ventana sensores IR/color
      // fijación del soporte de sensores inferiores
      for (y = [-15, 15]) translate([80, y]) circle(d = 3.4);
    } else {
      // ESP32 DevKit (55x28) – 4 agujeros M2.5 (sobre separadores de nylon)
      for (x = [-23.5, 23.5], y = [-11.5, 11.5]) translate([-10 + x, y]) circle(d = 2.8);
      // servo SG90 frontal (ventana 23x12.5)
      translate([80, 0]) square([12.6, 23.2], center = true);
      for (y = [-14, 14]) translate([80, y]) circle(d = 2.2);
      // mástil de brújula (trasero) y pasacables
      for (y = [-8, 8]) translate([-80, y]) circle(d = 3.4);
      translate([40, 0]) offset(r = 3) square([10, 34], center = true);
      // interruptor de encendido y conector de carga
      translate([-92, -40]) square([13, 8.5], center = true);
      translate([-92, 40]) circle(d = 8);
    }
  }
}

module placa(sup = false) { linear_extrude(T) placa2d(sup); }

module motor_tt(lado) {   // lado = +1 izquierda (y+), -1 derecha
  color("gold") translate([0, lado * 52, Z_BASE - MOTOR[2] / 2]) cube([MOTOR[0], MOTOR[1], MOTOR[2]], center = true);
  color("white") translate([0, lado * 52, RUEDA_D / 2]) rotate([-lado * 90, 0, 0]) cylinder(d = 5.4, h = 30);
}

module rueda(lado) {
  translate([0, lado * (W / 2 + 3 + RUEDA_A / 2), RUEDA_D / 2]) rotate([90, 0, 0]) {
    color("#222") difference() { cylinder(d = RUEDA_D, h = RUEDA_A, center = true);
                                 cylinder(d = 40, h = RUEDA_A + 1, center = true); }
    color("yellow") cylinder(d = 40, h = RUEDA_A - 4, center = true);
  }
}

module separador(x, y) { color("silver") translate([x, y, Z_BASE + T]) cylinder(d = 5, h = SEP, $fn = 6); }

// Soporte impreso que baja los sensores TCRT5000 (8 mm del piso) y TCS34725 (5 mm)
module soporte_sensores() {
  h = Z_BASE - 8;
  difference() {
    union() {
      translate([-6, -22, 0]) cube([12, 44, 4]);                       // brida a la placa
      translate([-6, -22, -h + 4]) cube([4, 44, h]);                   // pared
      translate([-6, -22, -h + 4]) cube([20, 44, 3]);                  // repisa IR (3 sensores)
      translate([-22, -12, -h + 1]) cube([16, 24, 3]);                 // repisa color (más baja)
      translate([-22, -12, -h + 1]) difference() {                     // faldón anti-luz ambiente
        cube([16, 24, 4]); translate([1.5, 1.5, -1]) cube([13, 21, 6]); }
    }
    for (y = [-15, 15]) translate([0, y, -1]) cylinder(d = 3.4, h = 6);
    for (y = [-15, 0, 15]) translate([8, y, -h]) cylinder(d = 3, h = 10);
    translate([-14, 0, -h - 1]) cylinder(d = 9, h = 8);                 // ventana del sensor de color
  }
}

module mastil() {   // tubo PLA 80 mm, sin piezas metálicas cerca del magnetómetro
  difference() {
    union() {
      translate([-10, -14, 0]) cube([20, 28, 4]);
      translate([0, 0, 0]) cylinder(d = 12, h = MASTIL_H);
      translate([-8, -10, MASTIL_H]) cube([16, 20, 3]);                // cama del GY-271
    }
    for (y = [-8, 8]) translate([0, y, -1]) cylinder(d = 3.4, h = 6);
    translate([0, 0, -1]) cylinder(d = 6, h = MASTIL_H + 5);           // paso de cables I2C
  }
}

module soporte_sonar() {   // escuadra HC-SR04 sobre el horn del servo
  difference() {
    union() { cube([10, 50, 3]); translate([7, 0, 0]) cube([3, 50, 24]); }
    for (y = [12, 38]) translate([6, y, 12]) rotate([0, 90, 0]) cylinder(d = 16.5, h = 6);
    translate([5, 25, -1]) cylinder(d = 2.5, h = 5);
  }
}

module ensamble() {
  // placas
  color("BurlyWood") translate([0, 0, Z_BASE]) placa(false);
  color("LightBlue", 0.75) translate([0, 0, Z_SUP]) placa(true);
  for (x = [-85, 0, 85], y = [-58, 58]) separador(x, y);
  // tracción
  for (sx = [-1, 1], sy = [-1, 1]) translate([sx * EJE_X, 0, 0]) { motor_tt(sy); rueda(sy); }
  // batería 2x18650 + BMS, puente H y regulador en la placa base
  color("RoyalBlue") translate([0, 0, Z_BASE + T + 10]) cube([77, 41, 20], center = true);
  color("Red") translate([55, -30, Z_BASE + T + 2]) cube([20, 20, 4], center = true);          // TB6612FNG
  color("DarkGreen") translate([-55, 30, Z_BASE + T + 6]) cube([43, 21, 12], center = true);   // buck 5 V
  // placa superior: ESP32, protoboard de distribución, servo + sonar, mástil
  color("#333") translate([-10, 0, Z_SUP + T + 6]) cube([55, 28, 8], center = true);           // ESP32
  color("Ivory") translate([-10, 0, Z_SUP + T + 1]) cube([70, 46, 2], center = true);          // PCB perforada
  color("Blue") translate([80, 0, Z_SUP + T - 15]) cube([12.2, 23, 29], center = true);        // SG90
  color("DeepSkyBlue") translate([86, 0, Z_SUP + T + 22]) cube([4, 45, 20], center = true);    // HC-SR04
  color("Silver") for (y = [-13, 13]) translate([90, y, Z_SUP + T + 22]) rotate([0, 90, 0]) cylinder(d = 16, h = 12);
  color("Orange") translate([-80, 0, Z_SUP + T]) mastil();
  color("Purple") translate([-80, 0, Z_SUP + T + MASTIL_H + 4]) cube([14, 13, 2], center = true); // GY-271
  // sensores inferiores
  color("Orange") translate([80, 0, Z_BASE]) soporte_sensores();
}

if (PARTE == "ensamble") ensamble();
else if (PARTE == "base_2d") placa2d(false);
else if (PARTE == "superior_2d") placa2d(true);
else if (PARTE == "soporte_sensores") rotate([180, 0, 0]) soporte_sensores();
else if (PARTE == "mastil") mastil();
else if (PARTE == "soporte_sonar") soporte_sonar();
