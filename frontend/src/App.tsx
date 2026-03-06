import React, { useState, useMemo, useEffect } from "react";
import { Layout } from "./components/Layout";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const API_BASE = (import.meta.env.VITE_API_URL || "http://localhost:3000") + "/api";

interface CardData {
  sheet_name: string;
  card_label: string;
  leader: string;
  cupo_mensual: string | number;
  valor_gastos: string | number;
  disponible: number;
}

interface MonthData {
  month_label: string;
  start_row: number;
  end_row: number;
}

interface ReportRow {
  no: any;
  fecha: string;
  nombre_negocio: string;
  nit: string;
  num_factura: string;
  centro_costos: string;
  concepto: string;
  valor_legalizado: string | number;
  url_drive: string;
  cufe: string;
  check_odoo_doc: string;
  check_odoo_pago: string;
  diferencia: string | number;
  observaciones: string;
  row_num: number;
}

export function App() {
  const [screen, setScreen] = useState<"cards" | "months" | "detail">("cards");
  const [cards, setCards] = useState<CardData[]>([]);
  const [selectedCard, setSelectedCard] = useState<CardData | null>(null);
  const [months, setMonths] = useState<MonthData[]>([]);
  const [selectedMonth, setSelectedMonth] = useState<MonthData | null>(null);
  const [reportRows, setReportRows] = useState<ReportRow[]>([]);
  const [loading, setLoading] = useState(false);

  // Filters
  const [filterStartDate, setFilterStartDate] = useState("");
  const [filterEndDate, setFilterEndDate] = useState("");
  const [filterHasDoc, setFilterHasDoc] = useState<"all" | "yes" | "no">("all");
  const [filterProveedor, setFilterProveedor] = useState("");
  const [filterNit, setFilterNit] = useState("");
  const [filterRef, setFilterRef] = useState("");

  // Fetch Cards on Mount
  useEffect(() => {
    setLoading(true);
    fetch(`${API_BASE}/cards/`)
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) {
          setCards(data);
        }
        setLoading(false);
      })
      .catch(err => {
        console.error("Error fetching cards:", err);
        setLoading(false);
      });
  }, []);

  const handleCardClick = (card: CardData) => {
    setSelectedCard(card);
    setLoading(true);
    fetch(`${API_BASE}/cards/${card.sheet_name}/months/`)
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) {
          setMonths(data);
        }
        setScreen("months");
        setLoading(false);
      })
      .catch(err => {
        console.error("Error fetching months:", err);
        setLoading(false);
      });
  };

  const handleMonthClick = (month: MonthData) => {
    setSelectedMonth(month);
    setLoading(true);
    fetch(`${API_BASE}/cards/${selectedCard?.sheet_name}/report/?start_row=${month.start_row}&end_row=${month.end_row}`)
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) {
          setReportRows(data);
        }
        setScreen("detail");
        setLoading(false);
      })
      .catch(err => {
        console.error("Error fetching report rows:", err);
        setLoading(false);
      });
  };

  const filteredData = useMemo(() => {
    return reportRows.filter(item => {
      const matchDate = (!filterStartDate || item.fecha >= filterStartDate) &&
        (!filterEndDate || item.fecha <= filterEndDate);
      const matchDoc = filterHasDoc === "all" ||
        (filterHasDoc === "yes" && item.url_drive) ||
        (filterHasDoc === "no" && !item.url_drive);
      const matchProveedor = !filterProveedor || String(item.nombre_negocio || "").toLowerCase().includes(filterProveedor.toLowerCase());
      const matchNit = !filterNit || String(item.nit || "").toLowerCase().includes(filterNit.toLowerCase());
      const matchRef = !filterRef || String(item.num_factura || "").toLowerCase().includes(filterRef.toLowerCase());

      return matchDate && matchDoc && matchProveedor && matchNit && matchRef;
    });
  }, [reportRows, filterStartDate, filterEndDate, filterHasDoc, filterProveedor, filterNit, filterRef]);

  const formatCurrency = (val: any) => {
    const num = parseFloat(String(val).replace(/[^0-9.-]+/g, ""));
    return isNaN(num) ? "$0" : `$${num.toLocaleString()}`;
  };

  if (screen === "months" && selectedCard) {
    return (
      <Layout breadcrumb={`Solenium > Finanzas > Gestión de tarjetas > ${selectedCard.card_label}`}>
        <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-500">
          <Button variant="ghost" className="mb-2 -ml-2 text-muted-foreground hover:text-primary transition-colors font-extrabold" onClick={() => setScreen("cards")}>
            ← Volver a tarjetas
          </Button>
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-extrabold tracking-tight text-foreground uppercase">Historial: {selectedCard.card_label}</h1>
            {loading && <Badge variant="outline" className="animate-pulse">Cargando...</Badge>}
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {months.map((m, idx) => (
              <Card key={idx} className="group relative cursor-pointer border-none shadow-lg hover:shadow-2xl transition-all duration-500 rounded-[1.5rem] overflow-hidden" onClick={() => handleMonthClick(m)}>
                <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-solenium-blue/10 group-hover:from-primary group-hover:to-solenium-blue transition-all duration-500 opacity-50 group-hover:opacity-100" />
                <CardHeader className="relative p-6">
                  <CardTitle className="flex justify-between items-center text-lg text-foreground group-hover:text-white font-extrabold uppercase transition-colors">
                    <span>{m.month_label}</span>
                    <Badge variant="secondary" className="font-extrabold group-hover:bg-white group-hover:text-primary">Ver Reporte</Badge>
                  </CardTitle>
                </CardHeader>
              </Card>
            ))}
          </div>
        </div>
      </Layout>
    );
  }

  if (screen === "detail" && selectedCard && selectedMonth) {
    return (
      <Layout breadcrumb={`Solenium > Finanzas > Gestión de tarjetas > ${selectedCard.card_label} > ${selectedMonth.month_label}`}>
        <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-500">
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <Button variant="ghost" className="mb-1 -ml-2 text-muted-foreground hover:text-primary transition-colors font-extrabold" onClick={() => setScreen("months")}>
                  ← Volver a meses
                </Button>
                <div className="flex items-center gap-3">
                  <h1 className="text-2xl font-extrabold tracking-tight text-foreground uppercase">{selectedCard.card_label} - {selectedMonth.month_label}</h1>
                  {loading && <Badge variant="outline" className="animate-pulse">Actualizando...</Badge>}
                </div>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" className="text-xs font-extrabold hover:bg-muted" onClick={() => {
                  setFilterStartDate(""); setFilterEndDate(""); setFilterHasDoc("all"); setFilterProveedor(""); setFilterNit(""); setFilterRef("");
                }}>Restaurar Filtros</Button>
                <Button variant="default" className="text-xs font-extrabold shadow-lg shadow-primary/20 hover:scale-105 active:scale-95 transition-all">Exportar Reporte</Button>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4 p-5 rounded-2xl bg-card border border-border shadow-sm ring-1 ring-border/5">
              <div className="flex flex-col gap-2"><label className="text-[10px] font-extrabold uppercase tracking-[0.1em] opacity-40 ml-1">Desde</label><input type="date" value={filterStartDate} onChange={(e) => setFilterStartDate(e.target.value)} className="w-full bg-muted/30 border border-transparent hover:border-primary/30 rounded-xl px-3 py-2 text-xs outline-none focus:border-primary focus:bg-background transition-all font-extrabold" /></div>
              <div className="flex flex-col gap-2"><label className="text-[10px] font-extrabold uppercase tracking-[0.1em] opacity-40 ml-1">Hasta</label><input type="date" value={filterEndDate} onChange={(e) => setFilterEndDate(e.target.value)} className="w-full bg-muted/30 border border-transparent hover:border-primary/30 rounded-xl px-3 py-2 text-xs outline-none focus:border-primary focus:bg-background transition-all font-extrabold" /></div>
              <div className="flex flex-col gap-2"><label className="text-[10px] font-extrabold uppercase tracking-[0.1em] opacity-40 ml-1">Proveedor</label><input type="text" placeholder="G. Solar..." value={filterProveedor} onChange={(e) => setFilterProveedor(e.target.value)} className="w-full bg-muted/30 border border-transparent hover:border-primary/30 rounded-xl px-3 py-2 text-xs outline-none focus:border-primary focus:bg-background transition-all font-extrabold" /></div>
              <div className="flex flex-col gap-2"><label className="text-[10px] font-extrabold uppercase tracking-[0.1em] opacity-40 ml-1">NIT/Cédula</label><input type="text" placeholder="123..." value={filterNit} onChange={(e) => setFilterNit(e.target.value)} className="w-full bg-muted/30 border border-transparent hover:border-primary/30 rounded-xl px-3 py-2 text-xs outline-none focus:border-primary focus:bg-background transition-all font-extrabold" /></div>
              <div className="flex flex-col gap-2"><label className="text-[10px] font-extrabold uppercase tracking-[0.1em] opacity-40 ml-1">Referencia</label><input type="text" placeholder="FE-..." value={filterRef} onChange={(e) => setFilterRef(e.target.value)} className="w-full bg-muted/30 border border-transparent hover:border-primary/30 rounded-xl px-3 py-2 text-xs outline-none focus:border-primary focus:bg-background transition-all font-extrabold" /></div>
              <div className="flex flex-col gap-2"><label className="text-[10px] font-extrabold uppercase tracking-[0.1em] opacity-40 ml-1">Soporte</label><select value={filterHasDoc} onChange={(e) => setFilterHasDoc(e.target.value as any)} className="w-full bg-muted/30 border border-transparent hover:border-primary/30 rounded-xl px-3 py-2 text-xs outline-none focus:border-primary focus:bg-background transition-all cursor-pointer font-extrabold"><option value="all">Ver todos</option><option value="yes">Con documento</option><option value="no">Sin documento</option></select></div>
            </div>
          </div>

          <Card className="border-border/50 shadow-sm overflow-hidden whitespace-nowrap rounded-2xl">
            <div className="overflow-x-auto">
              <table className="w-full text-[10px] text-left border-collapse">
                <thead className="bg-muted border-b border-border font-extrabold uppercase tracking-tighter opacity-80">
                  <tr>
                    <th className="px-2 py-4 border-r text-center w-8">No</th>
                    <th className="px-2 py-4 border-r">Fecha</th>
                    <th className="px-2 py-4 border-r">Proveedor</th>
                    <th className="px-2 py-4 border-r">NIT/Cédula</th>
                    <th className="px-2 py-4 border-r text-center">Ref. Factura</th>
                    <th className="px-2 py-4 border-r">C. Costos</th>
                    <th className="px-2 py-4 border-r text-right">Legalizado</th>
                    <th className="px-2 py-4 border-r">Descripción</th>
                    <th className="px-2 py-4 border-r text-center">Pago</th>
                    <th className="px-2 py-4 border-r">Comentarios Admin</th>
                    <th className="px-2 py-4 border-r">CUFE</th>
                    <th className="px-2 py-4 border-r text-center w-8">Drive</th>
                    <th className="px-2 py-4 text-center">Odoo</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {filteredData.map((item, idx) => (
                    <tr key={idx} className="hover:bg-primary/5 transition-colors group">
                      <td className="px-2 py-2 border-r text-center font-mono opacity-40">{item.no}</td>
                      <td className="px-2 py-2 border-r">{item.fecha}</td>
                      <td className="px-2 py-2 border-r font-extrabold truncate max-w-[120px]">{item.nombre_negocio}</td>
                      <td className="px-2 py-2 border-r font-mono opacity-70">{item.nit}</td>
                      <td className="px-2 py-2 border-r text-center"><Badge variant="outline" className="text-[8px] font-extrabold">{item.num_factura}</Badge></td>
                      <td className="px-2 py-2 border-r">{item.centro_costos}</td>
                      <td className="px-2 py-2 border-r text-right font-extrabold text-primary">{formatCurrency(item.valor_legalizado)}</td>
                      <td className="px-2 py-2 border-r truncate max-w-[150px] font-medium">{item.concepto}</td>
                      <td className="px-2 py-2 border-r text-center"><input type="checkbox" checked={item.check_odoo_pago === "x"} readOnly className="size-3 accent-primary" /></td>
                      <td className="px-2 py-2 border-r truncate max-w-[120px] opacity-70">{item.observaciones || "-"}</td>
                      <td className="px-2 py-2 border-r font-mono text-[7px] max-w-[100px] truncate opacity-40">{item.cufe || "-"}</td>
                      <td className="px-2 py-2 border-r text-center">{item.url_drive ? <a href={item.url_drive} target="_blank" rel="noreferrer" className="hover:scale-125 inline-block transition-transform">📂</a> : "-"}</td>
                      <td className="px-2 py-2 text-center">
                        <div className="flex flex-col items-center">
                          {item.check_odoo_doc === "x" ? <span className="text-green-600 font-extrabold">✓</span> : <span className="opacity-30">×</span>}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="space-y-10 animate-in fade-in slide-in-from-bottom-4 duration-700">
        <div className="flex items-end justify-between">
          <div className="space-y-1">
            <h1 className="text-3xl font-extrabold tracking-tight text-foreground uppercase">Gestión de Cajas</h1>
            <p className="text-muted-foreground text-sm font-medium">Panel administrativo con métricas financieras en tiempo real.</p>
          </div>
          {loading && <Badge variant="outline" className="animate-pulse mb-1">Cargando datos...</Badge>}
        </div>

        <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {cards.map((card, idx) => (
            <Card key={idx} className="group relative overflow-hidden min-h-[16rem] border-none shadow-lg hover:shadow-2xl transition-all duration-500 cursor-pointer rounded-[2rem]" onClick={() => handleCardClick(card)}>
              <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-solenium-blue/20 group-hover:from-primary group-hover:to-solenium-blue transition-all duration-500 opacity-50 group-hover:opacity-100" />
              <CardContent className="relative h-full flex flex-col p-8">
                <div className="flex justify-between items-start mb-4">
                  <div className="text-4xl group-hover:scale-110 transition-transform">💳</div>
                  <Badge className="bg-white/20 text-foreground group-hover:bg-white group-hover:text-primary transition-colors font-extrabold uppercase">ACTIVA</Badge>
                </div>

                <div className="space-y-1 mb-6">
                  <CardTitle className="text-2xl font-extrabold uppercase tracking-[0.1em] group-hover:text-white transition-colors">
                    {card.card_label}
                  </CardTitle>
                  <p className="text-[10px] font-mono font-extrabold opacity-40 group-hover:text-white/80 transition-colors uppercase tracking-widest leading-tight">Líder: {card.leader}</p>
                </div>

                <div className="space-y-4 mt-auto">
                  <div className="flex justify-between items-center text-[10px] font-extrabold uppercase tracking-widest group-hover:text-white/80 transition-colors">
                    <span>Cupo Mensual</span>
                    <span className="group-hover:text-white">{formatCurrency(card.cupo_mensual)}</span>
                  </div>
                  <div className="space-y-2">
                    <div className="flex justify-between text-[10px] font-extrabold uppercase tracking-widest group-hover:text-white transition-colors">
                      <span>Disponible</span>
                      <span>{formatCurrency(card.disponible)}</span>
                    </div>
                    <div className="h-1.5 w-full bg-black/5 group-hover:bg-white/20 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-primary group-hover:bg-white transition-all duration-1000"
                        style={{ width: `${Math.min(100, (card.disponible / (parseFloat(String(card.cupo_mensual).replace(/[^0-9.-]+/g, "")) || 1)) * 100)}%` }}
                      />
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </Layout>
  );
}

export default App;
