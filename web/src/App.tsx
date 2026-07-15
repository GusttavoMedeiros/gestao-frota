import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import {
  AlertTriangle,
  BarChart3,
  Bell,
  CheckCircle2,
  ChevronRight,
  ClipboardList,
  CreditCard,
  ExternalLink,
  FileText,
  Fuel,
  LayoutDashboard,
  Loader2,
  LogOut,
  Menu,
  Pencil,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  Truck,
  Trash2,
  UserRound,
  Users,
  Wrench,
  X
} from 'lucide-react';
import {
  deleteRecord,
  friendlyFleetError,
  getDocumentUrl,
  loadFleetData,
  removeDocument,
  saveRecord,
  updateSettings,
  uploadDocument
} from './lib/fleetApi';
import { apiConfigured, getApiSession, loginApi, logoutApi, type ApiSession } from './lib/api';
import { emptyFleetData, mockFleetData } from './data/mockData';
import { localISODate } from './lib/date';
import type { FleetData, ScreenKey } from './types';

const navigation = [
  { key: 'dashboard', label: 'Dashboard', mobileLabel: 'Dashboard', icon: LayoutDashboard },
  { key: 'veiculos', label: 'Veiculos', mobileLabel: 'Veiculos', icon: Truck },
  { key: 'motoristas', label: 'Motoristas', mobileLabel: 'Motoristas', icon: Users },
  { key: 'abastecimentos', label: 'Abastecimentos', mobileLabel: 'Abastec.', icon: Fuel },
  { key: 'manutencoes', label: 'Manutencoes', mobileLabel: 'Manut.', icon: Wrench },
  { key: 'despesas', label: 'Despesas', mobileLabel: 'Despesas', icon: CreditCard },
  { key: 'documentos', label: 'Documentos', mobileLabel: 'Docs', icon: FileText },
  { key: 'relatorios', label: 'Relatorios', mobileLabel: 'Relat.', icon: BarChart3 },
  { key: 'configuracoes', label: 'Configuracoes', mobileLabel: 'Config.', icon: Settings }
] as const;

const mobileNavigation = navigation.slice(0, 5);

const currencyFormatter = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL'
});

const numberFormatter = new Intl.NumberFormat('pt-BR');

function App() {
  const [session, setSession] = useState<ApiSession | null>(null);
  const [demoMode, setDemoMode] = useState(false);
  const [authLoading, setAuthLoading] = useState(true);
  const [dataLoading, setDataLoading] = useState(false);
  const [screen, setScreen] = useState<ScreenKey>('dashboard');
  const [fleetData, setFleetData] = useState<FleetData>(emptyFleetData);
  const [warning, setWarning] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingRecord, setEditingRecord] = useState<object | null>(null);
  const [search, setSearch] = useState('');
  const [toast, setToast] = useState<ToastState | null>(null);

  useEffect(() => {
    if (!apiConfigured) {
      setAuthLoading(false);
      return;
    }
    getApiSession().then(setSession).finally(() => setAuthLoading(false));
  }, []);

  useEffect(() => {
    if (demoMode) {
      setFleetData(mockFleetData);
      setWarning(null);
      return;
    }

    if (!session) return;

    setFleetData(emptyFleetData);
    setDataLoading(true);
    loadFleetData(session)
      .then(async (result) => {
        if (result.unauthorized) {
          logoutApi();
          setSession(null);
          return;
        }
        setFleetData(result.data);
        setWarning(result.warning || null);
      })
      .finally(() => setDataLoading(false));
  }, [demoMode, session]);

  const activeNav = navigation.find((item) => item.key === screen) || navigation[0];
  const activeLabel = activeNav.label;
  const canCreate = !['dashboard', 'relatorios', 'configuracoes'].includes(screen);
  const appReady = demoMode || session;
  const visibleData = filterFleetData(fleetData, search);

  function navigate(nextScreen: ScreenKey) {
    setScreen(nextScreen);
    setDrawerOpen(false);
  }

  function openCreate() {
    setEditingRecord(null);
    setModalOpen(true);
  }

  function openEdit(record: object) {
    setEditingRecord(record);
    setModalOpen(true);
  }

  async function signOut() {
    logoutApi();
    setDemoMode(false);
    setSession(null);
    setScreen('dashboard');
  }

  async function reloadData() {
    if (!session) return;
    const result = await loadFleetData(session);
    setFleetData(result.data);
    setWarning(result.warning || null);
  }

  async function handleSave(payload: Record<string, string | number | null | undefined>, file?: File) {
    if (!session || demoMode) {
      setToast({ message: 'Modo demonstracao: alteracoes nao sao salvas.', tone: 'neutral' });
      setModalOpen(false);
      return;
    }

    const current = editingRecord as { id?: string; arquivo_path?: string | null } | null;
    let uploadedPath: string | null = null;

    if (screen === 'documentos' && file) {
      const upload = await uploadDocument(file, String(payload.tipo || 'outros'), session.user.id);
      if (upload.error || !upload.path) {
        setToast({ message: friendlyFleetError(upload.error), tone: 'error' });
        return;
      }
      uploadedPath = upload.path;
      payload.arquivo_path = uploadedPath;
    }

    const { error } = await saveRecord(screen, payload, current?.id);
    if (error) {
      if (uploadedPath) await removeDocument(uploadedPath);
      setToast({ message: friendlyFleetError(error), tone: 'error' });
      return;
    }

    if (uploadedPath && current?.arquivo_path) await removeDocument(current.arquivo_path);
    setModalOpen(false);
    setEditingRecord(null);
    setToast({ message: 'Registro salvo com sucesso.', tone: 'success' });
    await reloadData();
  }

  async function handleDelete(id: string, documentPath?: string | null) {
    if (!window.confirm('Excluir este registro? Esta acao nao pode ser desfeita.')) return;

    if (!session || demoMode) {
      setToast({ message: 'Modo demonstracao: alteracoes nao sao salvas.', tone: 'neutral' });
      return;
    }

    const { error } = await deleteRecord(screen, id);
    if (error) {
      setToast({ message: friendlyFleetError(error), tone: 'error' });
      return;
    }

    const storageResult = documentPath ? await removeDocument(documentPath) : null;
    setToast({
      message: storageResult?.error ? 'Registro excluido, mas o arquivo nao pode ser removido.' : 'Registro excluido.',
      tone: storageResult?.error ? 'error' : 'success'
    });
    await reloadData();
  }

  async function handleOpenDocument(path: string) {
    const { data, error } = await getDocumentUrl(path);
    if (error || !data?.signedUrl) {
      setToast({ message: friendlyFleetError(error), tone: 'error' });
      return;
    }
    window.open(data.signedUrl, '_blank', 'noopener,noreferrer');
  }

  async function handleSettingsSave(payload: Record<string, string>) {
    if (!session || demoMode) {
      setToast({ message: 'Modo demonstracao: alteracoes nao sao salvas.', tone: 'neutral' });
      return;
    }
    if (!fleetData.settings.empresa_id) {
      setToast({ message: 'Configuracao da empresa nao encontrada.', tone: 'error' });
      return;
    }

    const { error } = await updateSettings(fleetData.settings.empresa_id, payload);
    setToast({
      message: error ? friendlyFleetError(error) : 'Configuracoes salvas.',
      tone: error ? 'error' : 'success'
    });
    if (!error) await reloadData();
  }

  if (authLoading) {
    return <SplashScreen />;
  }

  if (!appReady) {
    return <LoginScreen onDemo={() => setDemoMode(true)} onLogin={setSession} />;
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${drawerOpen ? 'is-open' : ''}`}>
        <Brand />
        <nav className="nav-list" aria-label="Navegacao principal">
          {navigation.map((item) => {
            const Icon = item.icon;
            const active = item.key === screen;
            return (
              <button
                key={item.key}
                className={`nav-item ${active ? 'is-active' : ''}`}
                type="button"
                onClick={() => navigate(item.key)}
              >
                <Icon size={19} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <div>
            <strong>{demoMode ? 'Modo demonstracao' : session?.user.name}</strong>
            <span>{demoMode ? 'Dados locais' : 'API conectada'}</span>
          </div>
          <button className="icon-button" type="button" onClick={signOut} aria-label="Sair">
            <LogOut size={18} />
          </button>
        </div>
      </aside>

      <button
        className={`drawer-scrim ${drawerOpen ? 'is-open' : ''}`}
        type="button"
        onClick={() => setDrawerOpen(false)}
        aria-label="Fechar menu"
      />

      <main className="main-area">
        <header className="topbar">
          <div className="topbar-left">
            <button
              className="icon-button mobile-only"
              type="button"
              onClick={() => setDrawerOpen(true)}
              aria-label="Abrir menu"
            >
              <Menu size={20} />
            </button>
            <div>
              <span className="section-kicker">KG Frota</span>
              <h1>{activeLabel}</h1>
            </div>
          </div>
          <div className="topbar-actions">
            <div className="search-control">
              <Search size={17} />
              <input
                aria-label="Buscar"
                placeholder="Buscar placa, motorista, documento..."
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
            <button className="icon-button" type="button" aria-label="Alertas" onClick={() => setScreen('dashboard')}>
              <Bell size={18} />
              {fleetData.alerts.some((alert) => alert.situacao !== 'ok') && <span className="notification-dot" />}
            </button>
            {canCreate && (
              <button className="primary-button" type="button" onClick={openCreate}>
                <Plus size={18} />
                <span>Novo registro</span>
              </button>
            )}
          </div>
        </header>

        {warning && <InlineNotice tone="warning" message={warning} />}
        {dataLoading && <LoadingStrip />}

        <section key={screen} className="screen-area">
          {screen === 'dashboard' && <Dashboard data={visibleData} onNavigate={navigate} />}
          {screen === 'veiculos' && <VehiclesScreen data={visibleData} onCreate={openCreate} onEdit={openEdit} onDelete={handleDelete} />}
          {screen === 'motoristas' && <DriversScreen data={visibleData} onCreate={openCreate} onEdit={openEdit} onDelete={handleDelete} />}
          {screen === 'abastecimentos' && <FuelScreen data={visibleData} onCreate={openCreate} onEdit={openEdit} onDelete={handleDelete} />}
          {screen === 'manutencoes' && <MaintenanceScreen data={visibleData} onCreate={openCreate} onEdit={openEdit} onDelete={handleDelete} />}
          {screen === 'despesas' && <ExpensesScreen data={visibleData} onCreate={openCreate} onEdit={openEdit} onDelete={handleDelete} />}
          {screen === 'documentos' && (
            <DocumentsScreen
              data={visibleData}
              onCreate={openCreate}
              onEdit={openEdit}
              onDelete={handleDelete}
              onOpen={handleOpenDocument}
            />
          )}
          {screen === 'relatorios' && <ReportsScreen data={visibleData} />}
          {screen === 'configuracoes' && <SettingsScreen data={visibleData} onSave={handleSettingsSave} />}
        </section>
      </main>

      <nav className="mobile-nav" aria-label="Navegacao mobile">
        {mobileNavigation.map((item) => {
          const Icon = item.icon;
          const active = item.key === screen;
          return (
            <button
              key={item.key}
              className={active ? 'is-active' : ''}
              type="button"
              onClick={() => navigate(item.key)}
            >
              <Icon size={20} />
              <span>{item.mobileLabel}</span>
            </button>
          );
        })}
      </nav>

      {modalOpen && (
        <RecordModal
          screen={screen}
          data={fleetData}
          record={editingRecord}
          onClose={() => {
            setModalOpen(false);
            setEditingRecord(null);
          }}
          onSubmit={handleSave}
        />
      )}

      {toast && <Toast {...toast} onClose={() => setToast(null)} />}
    </div>
  );
}

function SplashScreen() {
  return (
    <div className="splash">
      <Brand />
      <Loader2 className="spin" size={28} />
      <p>Carregando operacao...</p>
    </div>
  );
}

function LoginScreen({ onDemo, onLogin }: { onDemo: () => void; onLogin: (session: ApiSession) => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!apiConfigured) {
      setMessage('API nao configurada. Use o modo demonstracao.');
      return;
    }

    setLoading(true);
    try {
      onLogin(await loginApi(username, password));
    } catch (error) {
      setMessage(friendlyFleetError(error));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-layout">
      <section className="login-panel">
        <Brand />
        <div className="login-copy">
          <h1>Controle profissional da frota em uma tela rapida.</h1>
          <p>
            Veiculos, motoristas, documentos, abastecimentos e custos em um PWA pensado para uso diario no celular.
          </p>
        </div>
        <form className="login-form" onSubmit={handleLogin}>
          <label>
            Usuario
            <input
              type="text"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="admin"
              required
            />
          </label>
          <label>
            Senha
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Sua senha"
              required
            />
          </label>
          {message && <InlineNotice tone="warning" message={message} />}
          <button className="primary-button is-wide" type="submit" disabled={loading}>
            {loading ? <Loader2 className="spin" size={18} /> : <ShieldCheck size={18} />}
            Entrar
          </button>
          <button className="ghost-button is-wide" type="button" onClick={onDemo}>
            Abrir demonstracao
          </button>
        </form>
      </section>
      <section className="login-showcase" aria-label="Resumo visual">
        <div className="showcase-card">
          <span>Saude da frota</span>
          <strong>87%</strong>
          <div className="progress-track">
            <span style={{ width: '87%' }} />
          </div>
        </div>
        <div className="showcase-grid">
          <MetricCard icon={Truck} label="Veiculos ativos" value="18" />
          <MetricCard icon={AlertTriangle} label="Alertas" value="9" tone="warning" />
          <MetricCard icon={Fuel} label="Abastecimentos" value="147" />
          <MetricCard icon={Wrench} label="Manutencoes" value="5" tone="warning" />
        </div>
      </section>
    </main>
  );
}

function Brand() {
  return (
    <div className="brand">
      <div className="brand-mark">
        <Truck size={22} />
      </div>
      <div>
        <strong>KG Frota</strong>
        <span>Gestao operacional</span>
      </div>
    </div>
  );
}

function Dashboard({ data, onNavigate }: { data: FleetData; onNavigate: (screen: ScreenKey) => void }) {
  const cost = data.dashboard.custo_mes ?? data.expenses.reduce((sum, item) => sum + Number(item.valor || 0), 0);
  const pendingAlerts = data.alerts.filter((item) => item.situacao !== 'ok');
  const recentActivity = [
    ...data.fuelLogs.map((log) => ({
      id: `fuel-${log.id}`,
      date: log.data,
      icon: Fuel,
      title: `${log.veiculos?.placa || 'Veiculo'} - ${log.posto || 'Abastecimento'}`,
      meta: `${formatDate(log.data)} - ${numberFormatter.format(log.litros)} L`,
      value: currencyFormatter.format(Number(log.valor_total || 0))
    })),
    ...data.maintenances.map((item) => ({
      id: `maintenance-${item.id}`,
      date: item.data,
      icon: Wrench,
      title: `${item.veiculos?.placa || 'Veiculo'} - ${item.descricao}`,
      meta: `${formatDate(item.data)} - ${item.categoria}`,
      value: item.status.replace('_', ' ')
    })),
    ...data.expenses.map((item) => ({
      id: `expense-${item.id}`,
      date: item.data,
      icon: CreditCard,
      title: `${item.veiculos?.placa || 'Sem veiculo'} - ${item.descricao}`,
      meta: `${formatDate(item.data)} - ${item.categoria}`,
      value: currencyFormatter.format(Number(item.valor || 0))
    }))
  ]
    .sort((a, b) => b.date.localeCompare(a.date))
    .slice(0, 6);

  return (
    <div className="dashboard-layout">
      <div className="metric-grid">
        <MetricCard icon={Truck} label="Veiculos ativos" value={String(data.dashboard.veiculos_ativos ?? data.vehicles.length)} />
        <MetricCard icon={Users} label="Motoristas ativos" value={String(data.dashboard.motoristas_ativos ?? data.drivers.length)} />
        <MetricCard icon={CreditCard} label="Custo do mes" value={currencyFormatter.format(cost)} />
        <MetricCard icon={AlertTriangle} label="Alertas abertos" value={String(data.dashboard.alertas_abertos ?? pendingAlerts.length)} tone="warning" />
      </div>

      <div className="content-grid">
        <section className="panel panel-large">
          <PanelHeader
            title="Operacao de hoje"
            actionLabel="Ver abastecimentos"
            onAction={() => onNavigate('abastecimentos')}
          />
          <div className="activity-list">
            {recentActivity.map((item) => (
              <RowItem
                key={item.id}
                icon={item.icon}
                title={item.title}
                meta={item.meta}
                value={item.value}
              />
            ))}
          </div>
        </section>

        <section className="panel">
          <PanelHeader title="Alertas criticos" actionLabel="Documentos" onAction={() => onNavigate('documentos')} />
          <div className="alert-list">
            {pendingAlerts.slice(0, 5).map((alert) => (
              <div className={`alert-card ${alert.situacao === 'vencido' ? 'is-danger' : ''}`} key={alert.referencia_id}>
                <AlertTriangle size={18} />
                <div>
                  <strong>{alert.titulo}</strong>
                  <span>{alert.dias_restantes < 0 ? 'Vencido' : `${alert.dias_restantes} dias restantes`}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="panel">
          <PanelHeader title="Custos por categoria" />
          <div className="bar-list">
            {data.reportCosts.map((item) => (
              <div className="bar-row" key={item.categoria}>
                <div>
                  <span>{item.categoria}</span>
                  <strong>{currencyFormatter.format(Number(item.total || 0))}</strong>
                </div>
                <div className="bar-track">
                  <span style={{ width: `${Math.min(100, Number(item.total || 0) / 500)}%` }} />
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function VehiclesScreen({ data, onCreate, onEdit, onDelete }: ScreenProps) {
  return (
    <ResourceScreen
      title="Controle de veiculos"
      description="Status, quilometragem e cadastro base da frota."
      emptyTitle="Nenhum veiculo cadastrado"
      count={data.vehicles.length}
      onCreate={onCreate}
    >
      <div className="card-grid">
        {data.vehicles.map((vehicle) => (
          <article className="resource-card" key={vehicle.id}>
            <div className="resource-card-header">
              <div className="plate">{vehicle.placa}</div>
              <StatusBadge status={vehicle.status} />
            </div>
            <h3>{[vehicle.marca, vehicle.modelo].filter(Boolean).join(' ') || 'Veiculo sem modelo'}</h3>
            <div className="detail-grid">
              <span>Tipo</span>
              <strong>{vehicle.tipo}</strong>
              <span>Ano</span>
              <strong>{vehicle.ano || '-'}</strong>
              <span>KM atual</span>
              <strong>{numberFormatter.format(Number(vehicle.km_atual || 0))}</strong>
            </div>
            <RecordActions onEdit={() => onEdit(vehicle)} onDelete={() => onDelete(vehicle.id)} />
          </article>
        ))}
      </div>
    </ResourceScreen>
  );
}

function DriversScreen({ data, onCreate, onEdit, onDelete }: ScreenProps) {
  return (
    <ResourceScreen
      title="Motoristas"
      description="CNH, validade, contato e disponibilidade dos condutores."
      emptyTitle="Nenhum motorista cadastrado"
      count={data.drivers.length}
      onCreate={onCreate}
    >
      <div className="table-panel">
        {data.drivers.map((driver) => (
          <RowItem
            key={driver.id}
            icon={UserRound}
            title={driver.nome}
            meta={`CNH ${driver.cnh_categoria || '-'} - vence ${driver.cnh_validade ? formatDate(driver.cnh_validade) : '-'}`}
            value={driver.status}
            onEdit={() => onEdit(driver)}
            onDelete={() => onDelete(driver.id)}
          />
        ))}
      </div>
    </ResourceScreen>
  );
}

function FuelScreen({ data, onCreate, onEdit, onDelete }: ScreenProps) {
  return (
    <ResourceScreen
      title="Abastecimentos"
      description="Lancamentos de combustivel com valor por litro calculado pelo banco."
      emptyTitle="Nenhum abastecimento lancado"
      count={data.fuelLogs.length}
      onCreate={onCreate}
    >
      <div className="table-panel">
        {data.fuelLogs.map((log) => (
          <RowItem
            key={log.id}
            icon={Fuel}
            title={`${log.veiculos?.placa || 'Veiculo'} - ${log.posto || 'Posto nao informado'}`}
            meta={`${formatDate(log.data)} - ${numberFormatter.format(log.km)} km - ${log.motoristas?.nome || 'Sem motorista'}`}
            value={currencyFormatter.format(Number(log.valor_total || 0))}
            onEdit={() => onEdit(log)}
            onDelete={() => onDelete(log.id)}
          />
        ))}
      </div>
    </ResourceScreen>
  );
}

function MaintenanceScreen({ data, onCreate, onEdit, onDelete }: ScreenProps) {
  return (
    <ResourceScreen
      title="Manutencoes"
      description="Preventivas, corretivas e proximos vencimentos por data ou KM."
      emptyTitle="Nenhuma manutencao cadastrada"
      count={data.maintenances.length}
      onCreate={onCreate}
    >
      <div className="table-panel">
        {data.maintenances.map((item) => (
          <RowItem
            key={item.id}
            icon={Wrench}
            title={`${item.veiculos?.placa || 'Veiculo'} - ${item.descricao}`}
            meta={`${formatDate(item.data)} - ${item.categoria} - ${item.oficina || 'Sem oficina'}`}
            value={item.status.replace('_', ' ')}
            onEdit={() => onEdit(item)}
            onDelete={() => onDelete(item.id)}
          />
        ))}
      </div>
    </ResourceScreen>
  );
}

function ExpensesScreen({ data, onCreate, onEdit, onDelete }: ScreenProps) {
  return (
    <ResourceScreen
      title="Despesas"
      description="Multas, seguros, pedagios, licenciamentos e outros custos."
      emptyTitle="Nenhuma despesa cadastrada"
      count={data.expenses.length}
      onCreate={onCreate}
    >
      <div className="table-panel">
        {data.expenses.map((item) => (
          <RowItem
            key={item.id}
            icon={CreditCard}
            title={`${item.categoria} - ${item.descricao}`}
            meta={`${formatDate(item.data)} - ${item.veiculos?.placa || 'Sem veiculo'}`}
            value={currencyFormatter.format(Number(item.valor || 0))}
            onEdit={() => onEdit(item)}
            onDelete={() => onDelete(item.id)}
          />
        ))}
      </div>
    </ResourceScreen>
  );
}

function DocumentsScreen({ data, onCreate, onEdit, onDelete, onOpen }: DocumentScreenProps) {
  return (
    <ResourceScreen
      title="Documentos"
      description="CRLV, CNH, seguro, IPVA, contratos e arquivos assinados."
      emptyTitle="Nenhum documento cadastrado"
      count={data.documents.length}
      onCreate={onCreate}
    >
      <div className="table-panel">
        {data.documents.map((item) => (
          <RowItem
            key={item.id}
            icon={FileText}
            title={`${item.tipo.toUpperCase()} - ${item.descricao || 'Documento'}`}
            meta={`${item.veiculos?.placa || item.motoristas?.nome || 'Sem vinculo'} - vence ${item.validade ? formatDate(item.validade) : '-'}`}
            value={item.arquivo_path ? 'Arquivo anexado' : 'Sem arquivo'}
            onOpen={item.arquivo_path ? () => onOpen(item.arquivo_path!) : undefined}
            onEdit={() => onEdit(item)}
            onDelete={() => onDelete(item.id, item.arquivo_path)}
          />
        ))}
      </div>
    </ResourceScreen>
  );
}

function ReportsScreen({ data }: { data: FleetData }) {
  const total = data.reportCosts.reduce((sum, item) => sum + Number(item.total || 0), 0);

  return (
    <div className="reports-layout">
      <section className="panel panel-large">
        <PanelHeader title="Resumo financeiro" />
        <div className="report-hero">
          <span>Total no periodo</span>
          <strong>{currencyFormatter.format(total)}</strong>
          <p>Custos consolidados por categoria no periodo atual.</p>
        </div>
        <div className="bar-list">
          {data.reportCosts.map((item) => (
            <div className="bar-row" key={item.categoria}>
              <div>
                <span>{item.categoria}</span>
                <strong>{currencyFormatter.format(Number(item.total || 0))}</strong>
              </div>
              <div className="bar-track">
                <span style={{ width: `${total ? (Number(item.total || 0) / total) * 100 : 0}%` }} />
              </div>
            </div>
          ))}
        </div>
      </section>
      <section className="panel">
        <PanelHeader title="Indicadores operacionais" />
        <div className="mini-stat-list">
          <MetricCard icon={Fuel} label="Abastecimentos" value={String(data.fuelLogs.length)} />
          <MetricCard icon={Wrench} label="Manutencoes" value={String(data.maintenances.length)} />
          <MetricCard icon={FileText} label="Documentos" value={String(data.documents.length)} />
        </div>
      </section>
    </div>
  );
}

function SettingsScreen({
  data,
  onSave
}: {
  data: FleetData;
  onSave: (payload: Record<string, string>) => Promise<void>;
}) {
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await onSave(Object.fromEntries(form.entries()) as Record<string, string>);
  }

  return (
    <div className="settings-layout">
      <section className="panel">
        <PanelHeader title="Parametros de alerta" />
        <form
          className="settings-list"
          key={data.settings.empresa_id || 'settings'}
          onSubmit={submit}
        >
          <label>
            Dias para aviso de vencimento
            <input
              name="dias_aviso_vencimento"
              type="number"
              min="0"
              defaultValue={data.settings.dias_aviso_vencimento}
              required
            />
          </label>
          <label>
            KM para aviso de manutencao
            <input
              name="km_aviso_manutencao"
              type="number"
              min="0"
              defaultValue={data.settings.km_aviso_manutencao}
              required
            />
          </label>
          <button className="primary-button" type="submit">Salvar configuracoes</button>
        </form>
      </section>
      <section className="panel">
        <PanelHeader title="Seguranca" />
        <div className="security-list">
          <CheckCircle2 size={19} />
          <span>Frontend prioriza chave publicavel e aceita anon durante a migracao.</span>
          <CheckCircle2 size={19} />
          <span>Service role nao aparece no cliente.</span>
          <CheckCircle2 size={19} />
          <span>RLS deve bloquear leitura/escrita indevida.</span>
        </div>
      </section>
    </div>
  );
}

function ResourceScreen({
  title,
  description,
  emptyTitle,
  count,
  onCreate,
  children
}: {
  title: string;
  description: string;
  emptyTitle: string;
  count: number;
  onCreate: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="resource-layout">
      <section className="resource-intro">
        <div>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
        <button className="primary-button" type="button" onClick={onCreate}>
          <Plus size={18} />
          Adicionar
        </button>
      </section>
      {count > 0 ? children : <EmptyState title={emptyTitle} />}
    </div>
  );
}

function RecordModal({
  screen,
  data,
  record,
  onClose,
  onSubmit
}: {
  screen: ScreenKey;
  data: FleetData;
  record: object | null;
  onClose: () => void;
  onSubmit: (payload: Record<string, string | number | null | undefined>, file?: File) => Promise<void>;
}) {
  const fields = getFields(screen, data);
  const recordValues = (record || {}) as Record<string, unknown>;
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(
      fields.map((field) => [
        field.name,
        recordValues[field.name] === null || recordValues[field.name] === undefined
          ? field.defaultValue || ''
          : String(recordValues[field.name])
      ])
    )
  );
  const [file, setFile] = useState<File>();
  const [loading, setLoading] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const modalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    const frame = window.requestAnimationFrame(() => {
      modalRef.current?.querySelector<HTMLElement>('.modal-form input, .modal-form select')?.focus();
    });
    return () => {
      window.cancelAnimationFrame(frame);
      previousFocus?.focus();
    };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const error = validateRecord(screen, values);
    if (error) {
      setValidationError(error);
      return;
    }
    setLoading(true);
    await onSubmit(values, file);
    setLoading(false);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      onClose();
      return;
    }
    if (event.key !== 'Tab') return;

    const focusable = Array.from(
      modalRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled)') || []
    );
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div
      className="modal-layer"
      role="dialog"
      aria-modal="true"
      aria-labelledby="record-modal-title"
      onKeyDown={handleKeyDown}
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <div className="modal-card" ref={modalRef}>
        <div className="modal-header">
          <div>
            <span>{record ? 'Editar registro' : 'Novo registro'}</span>
            <h2 id="record-modal-title">{navigation.find((item) => item.key === screen)?.label}</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Fechar">
            <X size={19} />
          </button>
        </div>
        <form className="modal-form" onSubmit={submit}>
          {fields.map((field) => (
            <label key={field.name}>
              {field.label}
              {field.type === 'select' ? (
                <select
                  value={values[field.name] || ''}
                  onChange={(event) => setValues((current) => ({ ...current, [field.name]: event.target.value }))}
                  required={field.required}
                >
                  <option value="">Selecione</option>
                  {field.options?.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              ) : field.type === 'file' ? (
                <input
                  type="file"
                  accept=".pdf,image/*"
                  onChange={(event) => setFile(event.target.files?.[0])}
                />
              ) : (
                <input
                  type={field.type}
                  value={values[field.name] || ''}
                  min={field.min}
                  step={field.step}
                  onChange={(event) => setValues((current) => ({ ...current, [field.name]: event.target.value }))}
                  required={field.required}
                />
              )}
            </label>
          ))}
          {validationError && <InlineNotice tone="warning" message={validationError} />}
          <div className="modal-actions">
            <button className="ghost-button" type="button" onClick={onClose}>
              Cancelar
            </button>
            <button className="primary-button" type="submit" disabled={loading}>
              {loading ? <Loader2 className="spin" size={18} /> : <CheckCircle2 size={18} />}
              Salvar
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

type Field = {
  name: string;
  label: string;
  type: 'text' | 'number' | 'date' | 'select' | 'file';
  required?: boolean;
  min?: string;
  step?: string;
  defaultValue?: string;
  options?: { value: string; label: string }[];
};

function getFields(screen: ScreenKey, data: FleetData): Field[] {
  const vehicleOptions = data.vehicles.map((vehicle) => ({
    value: vehicle.id,
    label: `${vehicle.placa} - ${vehicle.modelo || 'Veiculo'}`
  }));
  const driverOptions = data.drivers.map((driver) => ({ value: driver.id, label: driver.nome }));

  if (screen === 'veiculos') {
    return [
      { name: 'placa', label: 'Placa', type: 'text', required: true },
      { name: 'marca', label: 'Marca', type: 'text', required: true },
      { name: 'modelo', label: 'Modelo', type: 'text', required: true },
      { name: 'ano', label: 'Ano', type: 'number', min: '1950', required: true },
      { name: 'renavam', label: 'Renavam', type: 'text' },
      { name: 'chassi', label: 'Chassi', type: 'text' },
      {
        name: 'tipo',
        label: 'Tipo',
        type: 'select',
        required: true,
        defaultValue: 'caminhao',
        options: selectOptions(['caminhao', 'carro', 'moto', 'utilitario', 'outro'])
      },
      {
        name: 'status',
        label: 'Status',
        type: 'select',
        required: true,
        defaultValue: 'ativo',
        options: selectOptions(['ativo', 'inativo', 'vendido', 'manutencao'])
      }
    ];
  }

  if (screen === 'motoristas') {
    return [
      { name: 'nome', label: 'Nome', type: 'text', required: true },
      { name: 'cnh_numero', label: 'Numero da CNH', type: 'text', required: true },
      { name: 'cnh_categoria', label: 'Categoria', type: 'text', required: true },
      { name: 'cnh_validade', label: 'Validade da CNH', type: 'date' },
      { name: 'telefone', label: 'Telefone', type: 'text' },
      { name: 'status', label: 'Status', type: 'select', defaultValue: 'ativo', options: selectOptions(['ativo', 'inativo']) }
    ];
  }

  if (screen === 'abastecimentos') {
    return [
      { name: 'veiculo_id', label: 'Veiculo', type: 'select', required: true, options: vehicleOptions },
      { name: 'motorista_id', label: 'Motorista', type: 'select', options: driverOptions },
      { name: 'data', label: 'Data', type: 'date', required: true, defaultValue: today() },
      { name: 'km', label: 'KM', type: 'number', required: true, min: '0', step: '1' },
      { name: 'litros', label: 'Litros', type: 'number', required: true, min: '0.01', step: '0.01' },
      { name: 'valor_total', label: 'Valor total', type: 'number', required: true, min: '0', step: '0.01' },
      {
        name: 'tipo_combustivel',
        label: 'Combustivel',
        type: 'select',
        options: selectOptions(['diesel', 'diesel_s10', 'gasolina', 'etanol', 'gnv', 'arla', 'outro'])
      },
      { name: 'posto', label: 'Posto', type: 'text' },
      { name: 'observacao', label: 'Observacao', type: 'text' }
    ];
  }

  if (screen === 'manutencoes') {
    return [
      { name: 'veiculo_id', label: 'Veiculo', type: 'select', required: true, options: vehicleOptions },
      { name: 'tipo', label: 'Tipo', type: 'select', required: true, options: selectOptions(['preventiva', 'corretiva']) },
      {
        name: 'categoria',
        label: 'Categoria',
        type: 'select',
        required: true,
        options: selectOptions(['oleo', 'pneu', 'freio', 'motor', 'suspensao', 'eletrica', 'revisao', 'funilaria', 'outros'])
      },
      { name: 'descricao', label: 'Descricao', type: 'text', required: true },
      { name: 'data', label: 'Data', type: 'date', required: true, defaultValue: today() },
      { name: 'km', label: 'KM', type: 'number', min: '0' },
      { name: 'valor', label: 'Valor', type: 'number', min: '0', step: '0.01', defaultValue: '0' },
      { name: 'oficina', label: 'Oficina', type: 'text' },
      { name: 'proxima_data', label: 'Proxima manutencao', type: 'date' },
      { name: 'proxima_km', label: 'Proxima manutencao (KM)', type: 'number', min: '0' },
      {
        name: 'status',
        label: 'Status',
        type: 'select',
        required: true,
        defaultValue: 'agendada',
        options: selectOptions(['agendada', 'em_andamento', 'concluida'])
      }
    ];
  }

  if (screen === 'despesas') {
    return [
      { name: 'veiculo_id', label: 'Veiculo', type: 'select', options: vehicleOptions },
      {
        name: 'categoria',
        label: 'Categoria',
        type: 'select',
        required: true,
        options: selectOptions(['ipva', 'seguro', 'multa', 'pedagio', 'licenciamento', 'financiamento', 'outros'])
      },
      { name: 'descricao', label: 'Descricao', type: 'text', required: true },
      { name: 'data', label: 'Data', type: 'date', required: true, defaultValue: today() },
      { name: 'valor', label: 'Valor', type: 'number', min: '0', step: '0.01', required: true },
      { name: 'vencimento', label: 'Vencimento', type: 'date' },
      { name: 'status', label: 'Status', type: 'select', defaultValue: 'pendente', options: selectOptions(['pendente', 'pago']) }
    ];
  }

  if (screen === 'documentos') {
    return [
      { name: 'veiculo_id', label: 'Veiculo', type: 'select', options: vehicleOptions },
      { name: 'motorista_id', label: 'Motorista', type: 'select', options: driverOptions },
      {
        name: 'tipo',
        label: 'Tipo',
        type: 'select',
        required: true,
        options: selectOptions(['crlv', 'cnh', 'seguro', 'ipva', 'licenciamento', 'contrato', 'outros'])
      },
      { name: 'descricao', label: 'Descricao', type: 'text' },
      { name: 'validade', label: 'Validade', type: 'date' },
      { name: 'arquivo', label: 'Arquivo (PDF ou imagem)', type: 'file' }
    ];
  }

  return [];
}

function MetricCard({
  icon: Icon,
  label,
  value,
  tone = 'default'
}: {
  icon: typeof Truck;
  label: string;
  value: string;
  tone?: 'default' | 'warning';
}) {
  return (
    <article className={`metric-card ${tone === 'warning' ? 'is-warning' : ''}`}>
      <div className="metric-icon">
        <Icon size={20} />
      </div>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function PanelHeader({
  title,
  actionLabel,
  onAction
}: {
  title: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="panel-header">
      <h2>{title}</h2>
      {actionLabel && (
        <button type="button" onClick={onAction}>
          {actionLabel}
          <ChevronRight size={16} />
        </button>
      )}
    </div>
  );
}

function RowItem({
  icon: Icon,
  title,
  meta,
  value,
  onOpen,
  onEdit,
  onDelete
}: {
  icon: typeof Truck;
  title: string;
  meta: string;
  value: string;
  onOpen?: () => void;
  onEdit?: () => void;
  onDelete?: () => void;
}) {
  return (
    <article className="row-item">
      <div className="row-icon">
        <Icon size={18} />
      </div>
      <div>
        <strong>{title}</strong>
        <span>{meta}</span>
      </div>
      <em>{value}</em>
      {(onOpen || onEdit || onDelete) && (
        <RecordActions onOpen={onOpen} onEdit={onEdit} onDelete={onDelete} />
      )}
    </article>
  );
}

function RecordActions({
  onOpen,
  onEdit,
  onDelete
}: {
  onOpen?: () => void;
  onEdit?: () => void;
  onDelete?: () => void;
}) {
  return (
    <div className="record-actions">
      {onOpen && (
        <button type="button" onClick={onOpen} aria-label="Abrir arquivo" title="Abrir arquivo">
          <ExternalLink size={17} />
        </button>
      )}
      {onEdit && (
        <button type="button" onClick={onEdit} aria-label="Editar registro" title="Editar">
          <Pencil size={17} />
        </button>
      )}
      {onDelete && (
        <button className="is-danger" type="button" onClick={onDelete} aria-label="Excluir registro" title="Excluir">
          <Trash2 size={17} />
        </button>
      )}
    </div>
  );
}

function EmptyState({ title }: { title: string }) {
  return (
    <div className="empty-state">
      <ClipboardList size={32} />
      <h3>{title}</h3>
      <p>Adicione o primeiro registro para liberar indicadores e alertas.</p>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  return <span className={`status-badge status-${status}`}>{status.replace('_', ' ')}</span>;
}

function InlineNotice({ tone, message }: { tone: 'warning' | 'neutral'; message: string }) {
  return (
    <div className={`inline-notice ${tone}`} role={tone === 'warning' ? 'alert' : 'status'}>
      <AlertTriangle size={18} />
      <span>{message}</span>
    </div>
  );
}

function LoadingStrip() {
  return (
    <div className="loading-strip">
      <span />
    </div>
  );
}

function Toast({ message, tone, onClose }: ToastState & { onClose: () => void }) {
  useEffect(() => {
    const timeout = window.setTimeout(onClose, 3600);
    return () => window.clearTimeout(timeout);
  }, [onClose]);

  return (
    <div className={`toast is-${tone}`} role={tone === 'error' ? 'alert' : 'status'} aria-live="polite">
      {tone === 'error' ? <AlertTriangle size={18} /> : <CheckCircle2 size={18} />}
      <span>{message}</span>
    </div>
  );
}

type ScreenProps = {
  data: FleetData;
  onCreate: () => void;
  onEdit: (record: object) => void;
  onDelete: (id: string, documentPath?: string | null) => void;
};

type DocumentScreenProps = ScreenProps & {
  onOpen: (path: string) => void;
};

type ToastState = {
  message: string;
  tone: 'success' | 'error' | 'neutral';
};

function selectOptions(values: string[]) {
  return values.map((value) => ({ value, label: value.replace('_', ' ') }));
}

function today() {
  return localISODate();
}

function formatDate(date: string) {
  return new Date(`${date}T12:00:00`).toLocaleDateString('pt-BR');
}

function validateRecord(screen: ScreenKey, values: Record<string, string>) {
  if (screen === 'abastecimentos' && Number(values.litros) <= 0) return 'Litros deve ser maior que zero.';
  if (screen === 'documentos' && Boolean(values.veiculo_id) === Boolean(values.motorista_id)) {
    return 'Selecione um veiculo ou um motorista, nunca os dois.';
  }
  return null;
}

function filterFleetData(data: FleetData, query: string): FleetData {
  const term = query.trim().toLocaleLowerCase('pt-BR');
  if (!term) return data;
  const matches = (value: unknown) => JSON.stringify(value).toLocaleLowerCase('pt-BR').includes(term);

  return {
    ...data,
    alerts: data.alerts.filter(matches),
    vehicles: data.vehicles.filter(matches),
    drivers: data.drivers.filter(matches),
    fuelLogs: data.fuelLogs.filter(matches),
    maintenances: data.maintenances.filter(matches),
    expenses: data.expenses.filter(matches),
    documents: data.documents.filter(matches),
    reportCosts: data.reportCosts.filter(matches)
  };
}

export default App;
