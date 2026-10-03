-- ============================================================================
--  VentaSys · 019 — Planilla (F12, T-1201)
--
--  QUINCE TABLAS, DE DOS CLASES
--
--  Cuatro son del país y no de una compañía: las tasas de la CCSS, los tramos
--  y los créditos de la renta, y la tabla de cesantía (RN-67). No llevan
--  company_id, como cabys_cache, porque son las mismas para todos los
--  patronos y las mantiene soporte. Las once restantes son de la compañía y
--  heredan el filtro de siempre.
--
--  LA ACCIÓN DE PERSONAL ES LA FUENTE (RN-90)
--
--  `personnel_actions` vive en el empleado, con sus fechas; la corrida las
--  toma y deja en `payroll_run_items` el tramo que aplicó, con `action_id` y
--  las fechas de ese tramo. De ahí salen el saldo de una deducción (RN-92) y
--  las líneas de incapacidad y permiso del archivo de la CCSS.
--
--  LA CORRIDA SE CONGELA (RN-66)
--
--  `payroll_run_items` guarda cada rubro con su base, su tasa y su monto. La
--  boleta se reimprime de ahí, nunca recalculando.
--
--  Los índices son los de los modelos (`model_payroll.py`). Idempotente.
-- ============================================================================

SET NAMES utf8mb4;

-- Globales, por país: sin company_id (como cabys_cache). Excepción en test_tenancy.
CREATE TABLE IF NOT EXISTS payroll_rates (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    country     CHAR(2)       NOT NULL,      -- 'CR'
    -- 'sem', 'ivm', 'banco_popular', 'asignaciones_familiares', 'imas', 'ina',
    -- 'fcl', 'rop', 'sick_leave_employer_rate', 'minimum_wage_unseizable', …
    concept     VARCHAR(40)   NOT NULL,
    payer       VARCHAR(8)    NOT NULL,      -- 'employee' | 'employer' | 'rule'
    -- Según el concepto: 0.0550 = 5,50 %, un número de días o un monto
    -- (el salario mínimo inembargable de RN-93). Por eso no cabe en (9,4).
    value       DECIMAL(14,4) NOT NULL,
    valid_from  DATE          NOT NULL,
    valid_to    DATE          NULL,
    source      VARCHAR(255)  NOT NULL,      -- la norma o la URL
    verified_at DATE          NOT NULL,      -- cuándo alguien lo comprobó
    UNIQUE KEY uq_payroll_rates (country, concept, payer, valid_from)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE IF NOT EXISTS income_tax_brackets (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    country     CHAR(2)       NOT NULL,
    valid_from  DATE          NOT NULL,
    valid_to    DATE          NULL,
    lower_bound DECIMAL(12,2) NOT NULL,
    upper_bound DECIMAL(12,2) NULL,        -- NULL: el último tramo
    rate        DECIMAL(5,4)  NOT NULL,
    source      VARCHAR(255)  NOT NULL,
    verified_at DATE          NOT NULL,
    UNIQUE KEY uq_income_tax_brackets (country, valid_from, lower_bound)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE IF NOT EXISTS income_tax_credits (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    country     CHAR(2)       NOT NULL,
    concept     VARCHAR(20)   NOT NULL,     -- 'child' | 'spouse'
    valid_from  DATE          NOT NULL,
    valid_to    DATE          NULL,
    amount      DECIMAL(12,2) NOT NULL,     -- mensual
    source      VARCHAR(255)  NOT NULL,
    verified_at DATE          NOT NULL,
    UNIQUE KEY uq_income_tax_credits (country, concept, valid_from)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE IF NOT EXISTS severance_table (              -- art. 29: días por año de antigüedad
    id          INT AUTO_INCREMENT PRIMARY KEY,
    country     CHAR(2)      NOT NULL,
    valid_from  DATE         NOT NULL,
    years_from  DECIMAL(4,2) NOT NULL,      -- 0.25 = tres meses
    years_to    DECIMAL(4,2) NULL,
    days        DECIMAL(5,2) NOT NULL,
    source      VARCHAR(255) NOT NULL,
    UNIQUE KEY uq_severance_table (country, valid_from, years_from)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- De acá en adelante, todo es de la compañía.
CREATE TABLE IF NOT EXISTS work_schedules (                  -- las jornadas (RN-94)
    id             INT AUTO_INCREMENT PRIMARY KEY,
    company_id     INT          NOT NULL,
    name           VARCHAR(80)  NOT NULL,
    -- 'monthly' | 'semimonthly' (quincenal) | 'biweekly' (bisemanal) | 'weekly'
    frequency      VARCHAR(12)  NOT NULL,
    shift          VARCHAR(8)   NOT NULL,      -- 'day' | 'mixed' | 'night'
    hours_per_day  DECIMAL(4,2) NOT NULL,      -- 8 · 7 · 6 por omisión (art. 136)
    workdays_per_week SMALLINT  NOT NULL DEFAULT 6,  -- las vacaciones (art. 153)
    rest_day_paid  TINYINT(1)   NOT NULL DEFAULT 1,  -- comercial (art. 152)
    first_cut_day  SMALLINT     NULL,          -- quincenal: corta el 8..15
    cut_weekday    SMALLINT     NULL,          -- semanal: 0 = lunes … 6 = domingo
    series_start   DATE         NULL,          -- bisemanal: primer día de la serie
    is_active      TINYINT(1)   NOT NULL DEFAULT 1,
    UNIQUE KEY uq_work_schedules_name (company_id, name),
    CONSTRAINT fk_ws_company FOREIGN KEY (company_id) REFERENCES companies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE IF NOT EXISTS positions (                       -- RN-95
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT          NOT NULL,
    name       VARCHAR(80)  NOT NULL,
    ccss_code  VARCHAR(4)   NOT NULL,          -- ocupación, cuatro dígitos
    ins_code   VARCHAR(5)   NOT NULL,
    is_active  TINYINT(1)   NOT NULL DEFAULT 1,
    UNIQUE KEY uq_positions_name (company_id, name),
    CONSTRAINT fk_positions_company FOREIGN KEY (company_id) REFERENCES companies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE IF NOT EXISTS ins_policies (                    -- pólizas de riesgos del trabajo
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT          NOT NULL,
    number     VARCHAR(20)  NOT NULL,
    rt_rate    DECIMAL(6,4) NOT NULL,          -- la prima que fija el INS
    is_default TINYINT(1)   NOT NULL DEFAULT 0,
    UNIQUE KEY uq_ins_policies_number (company_id, number),
    CONSTRAINT fk_insp_company FOREIGN KEY (company_id) REFERENCES companies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE IF NOT EXISTS employees (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    company_id          INT          NOT NULL,
    user_id             INT          NULL,               -- RN-72: opcional
    -- 'national' | 'dimex' | 'nite' | 'passport' | 'work_permit'. Palabras y
    -- no códigos: Hacienda, la CCSS y el INS numeran distinto, y cada
    -- adaptador de archivo traduce a los suyos.
    identification_type VARCHAR(12)  NOT NULL,
    identification      VARCHAR(30)  NOT NULL,
    first_name          VARCHAR(60)  NOT NULL,
    last_name_1         VARCHAR(40)  NOT NULL,
    last_name_2         VARCHAR(40)  NULL,               -- hay quien tiene uno solo
    insured_number      VARCHAR(25)  NULL,   -- CCSS; en nacionales, la cédula
    birth_date          DATE         NOT NULL,
    gender              CHAR(1)      NOT NULL,           -- 'F' | 'M'
    -- 'single' | 'married' | 'divorced' | 'widowed' | 'separated' |
    -- 'free_union' | 'unknown'
    marital_status      VARCHAR(10)  NOT NULL,
    nationality         CHAR(2)      NOT NULL,           -- ISO 3166, 'CR'
    phone               VARCHAR(20)  NULL,
    email               VARCHAR(120) NULL,
    is_pensioner        TINYINT(1)   NOT NULL DEFAULT 0, -- la CCSS cotiza distinto
    iban                VARCHAR(34)  NULL,
    hired_on            DATE         NOT NULL,
    terminated_on       DATE         NULL,
    -- 'resignation' | 'dismissal_with_cause' | 'dismissal_without_cause' |
    -- 'mutual' | 'end_of_contract'
    termination_cause   VARCHAR(30)  NULL,
    dependent_children  SMALLINT     NOT NULL DEFAULT 0, -- crédito fiscal
    spouse_credit       TINYINT(1)   NOT NULL DEFAULT 0,
    is_active           TINYINT(1)   NOT NULL DEFAULT 1,
    UNIQUE KEY uq_employees_identification (company_id, identification),
    CONSTRAINT fk_employees_company FOREIGN KEY (company_id) REFERENCES companies (id),
    CONSTRAINT fk_employees_user    FOREIGN KEY (user_id)    REFERENCES users (id_user)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE IF NOT EXISTS employment_contracts (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    company_id       INT           NOT NULL,
    employee_id      INT           NOT NULL,
    schedule_id      INT           NOT NULL,   -- la jornada: periodicidad y cortes
    position_id      INT           NOT NULL,
    ins_policy_id    INT           NULL,       -- NULL: la póliza por omisión
    valid_from       DATE          NOT NULL,
    valid_to         DATE          NULL,       -- un aumento lo cierra y abre otro
    period_salary    DECIMAL(12,2) NOT NULL,   -- el del periodo de su jornada
    solidarista_rate DECIMAL(5,4)  NULL,       -- aporte obrero, si hay
    INDEX idx_employment_contracts_employee (employee_id, valid_from),
    CONSTRAINT fk_ec_company  FOREIGN KEY (company_id)    REFERENCES companies (id),
    CONSTRAINT fk_ec_employee FOREIGN KEY (employee_id)   REFERENCES employees (id),
    CONSTRAINT fk_ec_schedule FOREIGN KEY (schedule_id)   REFERENCES work_schedules (id),
    CONSTRAINT fk_ec_position FOREIGN KEY (position_id)   REFERENCES positions (id),
    CONSTRAINT fk_ec_policy   FOREIGN KEY (ins_policy_id) REFERENCES ins_policies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE IF NOT EXISTS payroll_runs (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    company_id       INT         NOT NULL,
    -- 'regular' | 'aguinaldo' | 'settlement' | 'adjustment'
    kind             VARCHAR(12) NOT NULL,
    schedule_id      INT         NULL,      -- las regulares y sus ajustes
    period_from      DATE        NOT NULL,  -- sale del corte (RN-94); se guarda
    period_to        DATE        NOT NULL,  -- porque la corrida se congela
    pay_date         DATE        NOT NULL,
    -- 'draft' | 'approved' | 'paid' (RN-68)
    status           VARCHAR(10) NOT NULL DEFAULT 'draft',
    adjusts_run_id   INT         NULL,
    journal_entry_id INT         NULL,      -- RN-75, si hay contabilidad
    created_by       INT         NOT NULL,
    created_at       DATETIME    NOT NULL,
    approved_by      INT         NULL,
    approved_at      DATETIME    NULL,
    paid_by          INT         NULL,
    paid_at          DATETIME    NULL,
    INDEX idx_payroll_runs_period (company_id, period_from, kind),
    CONSTRAINT fk_pr_company  FOREIGN KEY (company_id)     REFERENCES companies (id),
    CONSTRAINT fk_pr_schedule FOREIGN KEY (schedule_id)    REFERENCES work_schedules (id),
    CONSTRAINT fk_pr_adjusts  FOREIGN KEY (adjusts_run_id) REFERENCES payroll_runs (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE IF NOT EXISTS payroll_run_lines (               -- un empleado en una corrida
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    company_id          INT           NOT NULL,
    run_id              INT           NOT NULL,
    employee_id         INT           NOT NULL,
    contract_id         INT           NOT NULL,
    gross               DECIMAL(12,2) NOT NULL,
    employee_deductions DECIMAL(12,2) NOT NULL,
    income_tax          DECIMAL(12,2) NOT NULL,
    other_deductions    DECIMAL(12,2) NOT NULL,  -- pensión, embargo, préstamos
    net                 DECIMAL(12,2) NOT NULL,
    employer_charges    DECIMAL(12,2) NOT NULL,
    UNIQUE KEY uq_payroll_run_lines (run_id, employee_id),
    CONSTRAINT fk_prl_company  FOREIGN KEY (company_id)  REFERENCES companies (id),
    CONSTRAINT fk_prl_run      FOREIGN KEY (run_id)      REFERENCES payroll_runs (id),
    CONSTRAINT fk_prl_employee FOREIGN KEY (employee_id) REFERENCES employees (id),
    CONSTRAINT fk_prl_contract FOREIGN KEY (contract_id) REFERENCES employment_contracts (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE IF NOT EXISTS personnel_actions (               -- RN-90: vive en el empleado
    id                INT AUTO_INCREMENT PRIMARY KEY,
    company_id        INT           NOT NULL,
    employee_id       INT           NOT NULL,
    -- 'overtime' | 'double_time' | 'bonus' | 'sick_leave_ccss' |
    -- 'sick_leave_ins' | 'maternity' | 'paid_leave' | 'unpaid_leave' |
    -- 'absence' | 'vacation' | 'deduction' | 'child_support' | 'garnishment' |
    -- 'raise' | 'position_change' | 'termination'
    kind              VARCHAR(20)   NOT NULL,
    starts_on         DATE          NOT NULL,
    ends_on           DATE          NULL,      -- NULL: recurrente sin fecha final
    hours             DECIMAL(8,2)  NULL,      -- horas extra y dobles
    days              DECIMAL(6,2)  NULL,      -- ausencias y vacaciones
    amount            DECIMAL(12,2) NULL,      -- bonificación, o cuota por corrida
    total_amount      DECIMAL(12,2) NULL,      -- lo pactado (RN-92); NULL: sin tope
    new_salary        DECIMAL(12,2) NULL,      -- aumento
    position_id       INT           NULL,      -- cambio de puesto
    is_recurring      TINYINT(1)    NOT NULL DEFAULT 0,
    memo              VARCHAR(160)  NULL,
    cancels_action_id INT           NULL,      -- la anulación (RN-91)
    suspended_at      DATETIME      NULL,
    suspended_by      INT           NULL,
    suspension_reason VARCHAR(160)  NULL,
    source            VARCHAR(8)    NOT NULL DEFAULT 'manual',  -- 'manual' | 'import' | 'system'
    created_by        INT           NOT NULL,
    created_at        DATETIME      NOT NULL,
    INDEX idx_personnel_actions_employee (employee_id, starts_on),
    CONSTRAINT fk_pa_company  FOREIGN KEY (company_id)        REFERENCES companies (id),
    CONSTRAINT fk_pa_employee FOREIGN KEY (employee_id)       REFERENCES employees (id),
    CONSTRAINT fk_pa_position FOREIGN KEY (position_id)       REFERENCES positions (id),
    CONSTRAINT fk_pa_cancels  FOREIGN KEY (cancels_action_id) REFERENCES personnel_actions (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- Los rubros SON las tasas congeladas (RN-66). La boleta se reimprime de acá.
CREATE TABLE IF NOT EXISTS payroll_run_items (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    company_id   INT           NOT NULL,
    line_id      INT           NOT NULL,
    -- 'base', 'overtime', 'double_time', 'sick_leave_subsidy', 'sem', 'ivm',
    -- 'income_tax', 'solidarista', 'garnishment', 'child_support', …
    concept      VARCHAR(40)   NOT NULL,
    payer        VARCHAR(8)    NOT NULL,    -- 'earning' | 'employee' | 'employer'
    base         DECIMAL(12,2) NOT NULL,
    -- NULL en los montos fijos (una deducción de ₡20 000).
    rate         DECIMAL(9,4)  NULL,
    amount       DECIMAL(12,2) NOT NULL,
    -- De qué acción sale y qué tramo de ella aplicó (RN-90). Las fechas son
    -- las de la acción, no las de la corrida: una retroactiva (RN-91) las trae
    -- de un periodo ya pagado, y el archivo de la CCSS las pide así.
    action_id    INT           NULL,
    quantity     DECIMAL(8,2)  NULL,        -- horas o días de ese tramo
    applied_from DATE          NULL,
    applied_to   DATE          NULL,
    INDEX idx_payroll_run_items_line (line_id),
    INDEX idx_payroll_run_items_action (action_id),
    CONSTRAINT fk_pri_company FOREIGN KEY (company_id) REFERENCES companies (id),
    CONSTRAINT fk_pri_line    FOREIGN KEY (line_id)    REFERENCES payroll_run_lines (id),
    CONSTRAINT fk_pri_action  FOREIGN KEY (action_id)  REFERENCES personnel_actions (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE IF NOT EXISTS vacation_movements (              -- el saldo es una suma (RN-70)
    id          INT AUTO_INCREMENT PRIMARY KEY,
    company_id  INT          NOT NULL,
    employee_id INT          NOT NULL,
    kind        VARCHAR(10)  NOT NULL,     -- 'accrual' | 'taken' | 'paid' | 'opening'
    days        DECIMAL(6,2) NOT NULL,
    on_date     DATE         NOT NULL,
    run_id      INT          NULL,
    action_id   INT          NULL,         -- el disfrute sale de una acción
    INDEX idx_vacation_movements_employee (employee_id, on_date),
    CONSTRAINT fk_vm_company  FOREIGN KEY (company_id)  REFERENCES companies (id),
    CONSTRAINT fk_vm_employee FOREIGN KEY (employee_id) REFERENCES employees (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- Lo devengado antes de VentaSys, mes a mes (RN-97). El aguinaldo suma los
-- meses de su periodo y la liquidación promedia los últimos seis: una sola
-- tabla sirve a los dos.
CREATE TABLE IF NOT EXISTS payroll_opening_earnings (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    company_id   INT           NOT NULL,
    employee_id  INT           NOT NULL,
    period_month DATE          NOT NULL,    -- el primer día del mes
    gross        DECIMAL(12,2) NOT NULL,
    imported_by  INT           NOT NULL,
    imported_at  DATETIME      NOT NULL,
    UNIQUE KEY uq_payroll_opening_earnings (employee_id, period_month),
    CONSTRAINT fk_poe_company  FOREIGN KEY (company_id)  REFERENCES companies (id),
    CONSTRAINT fk_poe_employee FOREIGN KEY (employee_id) REFERENCES employees (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;
