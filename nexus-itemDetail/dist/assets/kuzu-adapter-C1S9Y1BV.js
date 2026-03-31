let Ge, He, _e, De, $e, A, be, Le, Be;
let __tla = (async ()=>{
    const N = [
        "File",
        "Folder",
        "Function",
        "Class",
        "Interface",
        "Method",
        "CodeElement",
        "Community",
        "Process",
        "Struct",
        "Enum",
        "Macro",
        "Typedef",
        "Union",
        "Namespace",
        "Trait",
        "Impl",
        "TypeAlias",
        "Const",
        "Static",
        "Property",
        "Record",
        "Delegate",
        "Annotation",
        "Constructor",
        "Template",
        "Module"
    ], _ = "CodeRelation", L = "CodeEmbedding", K = `
CREATE NODE TABLE File (
  id STRING,
  name STRING,
  filePath STRING,
  content STRING,
  PRIMARY KEY (id)
)`, k = `
CREATE NODE TABLE Folder (
  id STRING,
  name STRING,
  filePath STRING,
  PRIMARY KEY (id)
)`, V = `
CREATE NODE TABLE Function (
  id STRING,
  name STRING,
  filePath STRING,
  startLine INT64,
  endLine INT64,
  isExported BOOLEAN,
  content STRING,
  PRIMARY KEY (id)
)`, z = `
CREATE NODE TABLE Class (
  id STRING,
  name STRING,
  filePath STRING,
  startLine INT64,
  endLine INT64,
  isExported BOOLEAN,
  content STRING,
  PRIMARY KEY (id)
)`, Q = `
CREATE NODE TABLE Interface (
  id STRING,
  name STRING,
  filePath STRING,
  startLine INT64,
  endLine INT64,
  isExported BOOLEAN,
  content STRING,
  PRIMARY KEY (id)
)`, q = `
CREATE NODE TABLE Method (
  id STRING,
  name STRING,
  filePath STRING,
  startLine INT64,
  endLine INT64,
  isExported BOOLEAN,
  content STRING,
  PRIMARY KEY (id)
)`, v = `
CREATE NODE TABLE CodeElement (
  id STRING,
  name STRING,
  filePath STRING,
  startLine INT64,
  endLine INT64,
  isExported BOOLEAN,
  content STRING,
  PRIMARY KEY (id)
)`, X = `
CREATE NODE TABLE Community (
  id STRING,
  label STRING,
  heuristicLabel STRING,
  keywords STRING[],
  description STRING,
  enrichedBy STRING,
  cohesion DOUBLE,
  symbolCount INT32,
  PRIMARY KEY (id)
)`, W = `
CREATE NODE TABLE Process (
  id STRING,
  label STRING,
  heuristicLabel STRING,
  processType STRING,
  stepCount INT32,
  communities STRING[],
  entryPointId STRING,
  terminalId STRING,
  PRIMARY KEY (id)
)`, l = (t)=>`
CREATE NODE TABLE \`${t}\` (
  id STRING,
  name STRING,
  filePath STRING,
  startLine INT64,
  endLine INT64,
  content STRING,
  PRIMARY KEY (id)
)`, Z = l("Struct"), J = l("Enum"), ee = l("Macro"), te = l("Typedef"), ne = l("Union"), oe = l("Namespace"), se = l("Trait"), re = l("Impl"), ce = l("TypeAlias"), ie = l("Const"), ae = l("Static"), Oe = l("Property"), le = l("Record"), Te = l("Delegate"), ue = l("Annotation"), Re = l("Constructor"), Me = l("Template"), de = l("Module"), Fe = `
CREATE REL TABLE ${_} (
  FROM File TO File,
  FROM File TO Folder,
  FROM File TO Function,
  FROM File TO Class,
  FROM File TO Interface,
  FROM File TO Method,
  FROM File TO CodeElement,
  FROM File TO \`Struct\`,
  FROM File TO \`Enum\`,
  FROM File TO \`Macro\`,
  FROM File TO \`Typedef\`,
  FROM File TO \`Union\`,
  FROM File TO \`Namespace\`,
  FROM File TO \`Trait\`,
  FROM File TO \`Impl\`,
  FROM File TO \`TypeAlias\`,
  FROM File TO \`Const\`,
  FROM File TO \`Static\`,
  FROM File TO \`Property\`,
  FROM File TO \`Record\`,
  FROM File TO \`Delegate\`,
  FROM File TO \`Annotation\`,
  FROM File TO \`Constructor\`,
  FROM File TO \`Template\`,
  FROM File TO \`Module\`,
  FROM Folder TO Folder,
  FROM Folder TO File,
  FROM Function TO Function,
  FROM Function TO Method,
  FROM Function TO Class,
  FROM Function TO Community,
  FROM Function TO \`Macro\`,
  FROM Function TO \`Struct\`,
  FROM Function TO \`Template\`,
  FROM Function TO \`Enum\`,
  FROM Function TO \`Namespace\`,
  FROM Function TO \`TypeAlias\`,
  FROM Function TO \`Module\`,
  FROM Function TO \`Impl\`,
  FROM Function TO Interface,
  FROM Function TO \`Constructor\`,
  FROM Class TO Method,
  FROM Class TO Function,
  FROM Class TO Class,
  FROM Class TO Interface,
  FROM Class TO Community,
  FROM Class TO \`Template\`,
  FROM Class TO \`TypeAlias\`,
  FROM Class TO \`Struct\`,
  FROM Class TO \`Enum\`,
  FROM Class TO \`Constructor\`,
  FROM Method TO Function,
  FROM Method TO Method,
  FROM Method TO Class,
  FROM Method TO Community,
  FROM Method TO \`Template\`,
  FROM Method TO \`Struct\`,
  FROM Method TO \`TypeAlias\`,
  FROM Method TO \`Enum\`,
  FROM Method TO \`Macro\`,
  FROM Method TO \`Namespace\`,
  FROM Method TO \`Module\`,
  FROM Method TO \`Impl\`,
  FROM Method TO Interface,
  FROM Method TO \`Constructor\`,
  FROM \`Template\` TO \`Template\`,
  FROM \`Template\` TO Function,
  FROM \`Template\` TO Method,
  FROM \`Template\` TO Class,
  FROM \`Template\` TO \`Struct\`,
  FROM \`Template\` TO \`TypeAlias\`,
  FROM \`Template\` TO \`Enum\`,
  FROM \`Template\` TO \`Macro\`,
  FROM \`Template\` TO Interface,
  FROM \`Template\` TO \`Constructor\`,
  FROM \`Module\` TO \`Module\`,
  FROM CodeElement TO Community,
  FROM Interface TO Community,
  FROM Interface TO Function,
  FROM Interface TO Method,
  FROM Interface TO Class,
  FROM Interface TO Interface,
  FROM Interface TO \`TypeAlias\`,
  FROM Interface TO \`Struct\`,
  FROM Interface TO \`Constructor\`,
  FROM \`Struct\` TO Community,
  FROM \`Struct\` TO \`Trait\`,
  FROM \`Struct\` TO Function,
  FROM \`Struct\` TO Method,
  FROM \`Enum\` TO Community,
  FROM \`Macro\` TO Community,
  FROM \`Macro\` TO Function,
  FROM \`Macro\` TO Method,
  FROM \`Module\` TO Function,
  FROM \`Module\` TO Method,
  FROM \`Typedef\` TO Community,
  FROM \`Union\` TO Community,
  FROM \`Namespace\` TO Community,
  FROM \`Trait\` TO Community,
  FROM \`Impl\` TO Community,
  FROM \`Impl\` TO \`Trait\`,
  FROM \`TypeAlias\` TO Community,
  FROM \`Const\` TO Community,
  FROM \`Static\` TO Community,
  FROM \`Property\` TO Community,
  FROM \`Record\` TO Community,
  FROM \`Delegate\` TO Community,
  FROM \`Annotation\` TO Community,
  FROM \`Constructor\` TO Community,
  FROM \`Constructor\` TO Interface,
  FROM \`Constructor\` TO Class,
  FROM \`Constructor\` TO Method,
  FROM \`Constructor\` TO Function,
  FROM \`Constructor\` TO \`Constructor\`,
  FROM \`Constructor\` TO \`Struct\`,
  FROM \`Constructor\` TO \`Macro\`,
  FROM \`Constructor\` TO \`Template\`,
  FROM \`Constructor\` TO \`TypeAlias\`,
  FROM \`Constructor\` TO \`Enum\`,
  FROM \`Constructor\` TO \`Impl\`,
  FROM \`Constructor\` TO \`Namespace\`,
  FROM \`Template\` TO Community,
  FROM \`Module\` TO Community,
  FROM Function TO Process,
  FROM Method TO Process,
  FROM Class TO Process,
  FROM Interface TO Process,
  FROM \`Struct\` TO Process,
  FROM \`Constructor\` TO Process,
  FROM \`Module\` TO Process,
  FROM \`Macro\` TO Process,
  FROM \`Impl\` TO Process,
  FROM \`Typedef\` TO Process,
  FROM \`TypeAlias\` TO Process,
  FROM \`Enum\` TO Process,
  FROM \`Union\` TO Process,
  FROM \`Namespace\` TO Process,
  FROM \`Trait\` TO Process,
  FROM \`Const\` TO Process,
  FROM \`Static\` TO Process,
  FROM \`Property\` TO Process,
  FROM \`Record\` TO Process,
  FROM \`Delegate\` TO Process,
  FROM \`Annotation\` TO Process,
  FROM \`Template\` TO Process,
  FROM CodeElement TO Process,
  type STRING,
  confidence DOUBLE,
  reason STRING,
  step INT32
)`, me = `
CREATE NODE TABLE ${L} (
  nodeId STRING,
  embedding FLOAT[384],
  PRIMARY KEY (nodeId)
)`, Ee = [
        K,
        k,
        V,
        z,
        Q,
        q,
        v,
        X,
        W,
        Z,
        J,
        ee,
        te,
        ne,
        oe,
        se,
        re,
        ce,
        ie,
        ae,
        Oe,
        le,
        Te,
        ue,
        Re,
        Me,
        de
    ], pe = [
        Fe
    ], Ce = [
        ...Ee,
        ...pe,
        me
    ], fe = (t)=>t.replace(/\r\n/g, `
`).replace(/\r/g, `
`).replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, "").replace(/[\uD800-\uDFFF]/g, "").replace(/[\uFFFE\uFFFF]/g, ""), i = (t)=>{
        if (t == null) return '""';
        let o = String(t);
        return o = fe(o), `"${o.replace(/"/g, '""')}"`;
    }, p = (t, o = -1)=>t == null ? String(o) : String(t), Se = (t)=>{
        if (!t || t.length === 0) return !1;
        const o = t.slice(0, 1e3);
        let n = 0;
        for(let e = 0; e < o.length; e++){
            const r = o.charCodeAt(e);
            (r < 9 || r > 13 && r < 32 || r === 127) && n++;
        }
        return n / o.length > .1;
    }, B = (t, o)=>{
        const n = t.properties.filePath, e = o.get(n);
        if (!e || t.label === "Folder") return "";
        if (Se(e)) return "[Binary file - content not stored]";
        if (t.label === "File") return e.length > 1e4 ? e.slice(0, 1e4) + `
... [truncated]` : e;
        const r = t.properties.startLine, s = t.properties.endLine;
        if (r === void 0 || s === void 0) return "";
        const c = e.split(`
`), T = 2, d = Math.max(0, r - T), R = Math.min(c.length - 1, s + T), F = c.slice(d, R + 1).join(`
`), f = 5e3;
        return F.length > f ? F.slice(0, f) + `
... [truncated]` : F;
    }, he = (t, o)=>{
        const e = [
            [
                "id",
                "name",
                "filePath",
                "content"
            ].join(",")
        ];
        for (const r of t){
            if (r.label !== "File") continue;
            const s = B(r, o);
            e.push([
                i(r.id),
                i(r.properties.name || ""),
                i(r.properties.filePath || ""),
                i(s)
            ].join(","));
        }
        return e.join(`
`);
    }, Ie = (t)=>{
        const n = [
            [
                "id",
                "name",
                "filePath"
            ].join(",")
        ];
        for (const e of t)e.label === "Folder" && n.push([
            i(e.id),
            i(e.properties.name || ""),
            i(e.properties.filePath || "")
        ].join(","));
        return n.join(`
`);
    }, h = (t, o, n)=>{
        const r = [
            [
                "id",
                "name",
                "filePath",
                "startLine",
                "endLine",
                "isExported",
                "content"
            ].join(",")
        ];
        for (const s of t){
            if (s.label !== o) continue;
            const c = B(s, n);
            r.push([
                i(s.id),
                i(s.properties.name || ""),
                i(s.properties.filePath || ""),
                p(s.properties.startLine, -1),
                p(s.properties.endLine, -1),
                s.properties.isExported ? "true" : "false",
                i(c)
            ].join(","));
        }
        return r.join(`
`);
    }, Ae = (t)=>{
        const n = [
            [
                "id",
                "label",
                "heuristicLabel",
                "keywords",
                "description",
                "enrichedBy",
                "cohesion",
                "symbolCount"
            ].join(",")
        ];
        for (const e of t){
            if (e.label !== "Community") continue;
            const s = `[${(e.properties.keywords || []).map((c)=>`'${c.replace(/'/g, "''")}'`).join(",")}]`;
            n.push([
                i(e.id),
                i(e.properties.name || ""),
                i(e.properties.heuristicLabel || ""),
                s,
                i(e.properties.description || ""),
                i(e.properties.enrichedBy || "heuristic"),
                p(e.properties.cohesion, 0),
                p(e.properties.symbolCount, 0)
            ].join(","));
        }
        return n.join(`
`);
    }, Ne = (t)=>{
        const n = [
            [
                "id",
                "label",
                "heuristicLabel",
                "processType",
                "stepCount",
                "communities",
                "entryPointId",
                "terminalId"
            ].join(",")
        ];
        for (const e of t){
            if (e.label !== "Process") continue;
            const s = `[${(e.properties.communities || []).map((c)=>`'${c.replace(/'/g, "''")}'`).join(",")}]`;
            n.push([
                i(e.id),
                i(e.properties.name || ""),
                i(e.properties.heuristicLabel || ""),
                i(e.properties.processType || ""),
                p(e.properties.stepCount, 0),
                i(s),
                i(e.properties.entryPointId || ""),
                i(e.properties.terminalId || "")
            ].join(","));
        }
        return n.join(`
`);
    }, ye = (t)=>{
        const n = [
            [
                "from",
                "to",
                "type",
                "confidence",
                "reason",
                "step"
            ].join(",")
        ];
        for (const e of t.relationships)n.push([
            i(e.sourceId),
            i(e.targetId),
            i(e.type),
            p(e.confidence, 1),
            i(e.reason),
            p(e.step, 0)
        ].join(","));
        return n.join(`
`);
    }, Pe = (t, o)=>{
        const n = Array.from(t.nodes), e = new Map;
        e.set("File", he(n, o)), e.set("Folder", Ie(n)), e.set("Function", h(n, "Function", o)), e.set("Class", h(n, "Class", o)), e.set("Interface", h(n, "Interface", o)), e.set("Method", h(n, "Method", o)), e.set("CodeElement", h(n, "CodeElement", o)), e.set("Community", Ae(n)), e.set("Process", Ne(n));
        const r = ye(t);
        return {
            nodes: e,
            relCSV: r
        };
    };
    let E = null, m = null, a = null;
    let I, x, we, ge;
    A = async ()=>{
        if (a) return {
            db: m,
            conn: a,
            kuzu: E
        };
        try {
            const t = await import("./index-poHdBmg0.js");
            E = t.default || t, await E.init();
            const o = 512 * 1024 * 1024;
            m = new E.Database(":memory:", o), a = new E.Connection(m);
            for (const n of Ce)try {
                await a.query(n);
            } catch  {}
            return {
                db: m,
                conn: a,
                kuzu: E
            };
        } catch (t) {
            throw t;
        }
    };
    Le = async (t, o)=>{
        const { conn: n, kuzu: e } = await A();
        try {
            const r = Pe(t, o), s = e.FS, c = [];
            for (const [O, M] of r.nodes.entries()){
                if (M.split(`
`).length <= 1) continue;
                const u = `/${O.toLowerCase()}.csv`;
                try {
                    await s.unlink(u);
                } catch  {}
                await s.writeFile(u, M), c.push({
                    table: O,
                    path: u
                });
            }
            const T = r.relCSV.split(`
`).slice(1).filter((O)=>O.trim()), d = T.length;
            for (const { table: O, path: M } of c){
                const u = ge(O, M);
                await n.query(u);
            }
            const R = new Set(N), F = (O)=>O.startsWith("comm_") ? "Community" : O.startsWith("proc_") ? "Process" : O.split(":")[0], f = (O)=>x.has(O) ? `\`${O}\`` : O;
            let $ = 0, b = 0;
            const G = new Map;
            for (const O of T)try {
                const M = O.match(/"([^"]*)","([^"]*)","([^"]*)",([0-9.]+),"([^"]*)",([0-9-]+)/);
                if (!M) continue;
                const [, u, C, y, P, w, g] = M, S = F(u), D = F(C);
                if (!R.has(S) || !R.has(D)) {
                    b++;
                    continue;
                }
                const Y = parseFloat(P) || 1, U = parseInt(g) || 0, j = `
          MATCH (a:${f(S)} {id: '${u.replace(/'/g, "''")}'}),
                (b:${f(D)} {id: '${C.replace(/'/g, "''")}'})
          CREATE (a)-[:${_} {type: '${y}', confidence: ${Y}, reason: '${w.replace(/'/g, "''")}', step: ${U}}]->(b)
        `;
                await n.query(j), $++;
            } catch  {
                b++;
                const u = O.match(/"([^"]*)","([^"]*)","([^"]*)",([0-9.]+),"([^"]*)"/);
                if (u) {
                    const [, C, y, P] = u, w = F(C), g = F(y), S = `${P}:${w}->` + g;
                    G.set(S, (G.get(S) || 0) + 1);
                }
            }
            let H = 0;
            for (const O of N)try {
                const u = await (await n.query(`MATCH (n:${O}) RETURN count(n) AS cnt`)).getNext(), C = u ? u.cnt ?? u[0] ?? 0 : 0;
                H += Number(C);
            } catch  {}
            for (const { path: O } of c)try {
                await s.unlink(O);
            } catch  {}
            return {
                success: !0,
                count: H
            };
        } catch  {
            return {
                success: !1,
                count: 0
            };
        }
    };
    I = `(HEADER=true, ESCAPE='"', DELIM=',', QUOTE='"', PARALLEL=false, auto_detect=false)`;
    x = new Set([
        "Struct",
        "Enum",
        "Macro",
        "Typedef",
        "Union",
        "Namespace",
        "Trait",
        "Impl",
        "TypeAlias",
        "Const",
        "Static",
        "Property",
        "Record",
        "Delegate",
        "Annotation",
        "Constructor",
        "Template",
        "Module"
    ]);
    we = (t)=>x.has(t) ? `\`${t}\`` : t;
    ge = (t, o)=>{
        const n = we(t);
        return t === "File" ? `COPY ${n}(id, name, filePath, content) FROM "${o}" ${I}` : t === "Folder" ? `COPY ${n}(id, name, filePath) FROM "${o}" ${I}` : t === "Community" ? `COPY ${n}(id, label, heuristicLabel, keywords, description, enrichedBy, cohesion, symbolCount) FROM "${o}" ${I}` : t === "Process" ? `COPY ${n}(id, label, heuristicLabel, processType, stepCount, communities, entryPointId, terminalId) FROM "${o}" ${I}` : `COPY ${n}(id, name, filePath, startLine, endLine, isExported, content) FROM "${o}" ${I}`;
    };
    _e = async (t)=>{
        a || await A();
        try {
            const o = await a.query(t), n = t.match(/RETURN\s+(.+?)(?:\s+ORDER|\s+LIMIT|\s+SKIP|\s*$)/is);
            let e = [];
            n && (e = n[1].split(",").map((c)=>{
                c = c.trim();
                const T = c.match(/\s+AS\s+(\w+)\s*$/i);
                if (T) return T[1];
                const d = c.match(/\.(\w+)\s*$/);
                if (d) return d[1];
                const R = c.match(/^(\w+)\s*\(/);
                return R ? R[1] : c.replace(/[^a-zA-Z0-9_]/g, "_");
            }));
            const r = [];
            for(; await o.hasNext();){
                const s = await o.getNext();
                if (Array.isArray(s) && e.length === s.length) {
                    const c = {};
                    for(let T = 0; T < s.length; T++)c[e[T]] = s[T];
                    r.push(c);
                } else r.push(s);
            }
            return r;
        } catch (o) {
            throw o;
        }
    };
    $e = async ()=>{
        if (!a) return {
            nodes: 0,
            edges: 0
        };
        try {
            let t = 0;
            for (const n of N)try {
                const r = await (await a.query(`MATCH (n:${n}) RETURN count(n) AS cnt`)).getNext();
                t += Number(r?.cnt ?? r?.[0] ?? 0);
            } catch  {}
            let o = 0;
            try {
                const e = await (await a.query(`MATCH ()-[r:${_}]->() RETURN count(r) AS cnt`)).getNext();
                o = Number(e?.cnt ?? e?.[0] ?? 0);
            } catch  {}
            return {
                nodes: t,
                edges: o
            };
        } catch  {
            return {
                nodes: 0,
                edges: 0
            };
        }
    };
    be = ()=>a !== null && m !== null;
    Ge = async ()=>{
        if (a) {
            try {
                await a.close();
            } catch  {}
            a = null;
        }
        if (m) {
            try {
                await m.close();
            } catch  {}
            m = null;
        }
        E = null;
    };
    He = async (t, o)=>{
        a || await A();
        try {
            const n = await a.prepare(t);
            if (!n.isSuccess()) {
                const s = await n.getErrorMessage();
                throw new Error(`Prepare failed: ${s}`);
            }
            const e = await a.execute(n, o), r = [];
            for(; await e.hasNext();){
                const s = await e.getNext();
                r.push(s);
            }
            return await n.close(), r;
        } catch (n) {
            throw n;
        }
    };
    De = async (t, o)=>{
        if (a || await A(), o.length === 0) return;
        const n = 4;
        for(let e = 0; e < o.length; e += n){
            const r = o.slice(e, e + n), s = await a.prepare(t);
            if (!s.isSuccess()) {
                const c = await s.getErrorMessage();
                throw new Error(`Prepare failed: ${c}`);
            }
            try {
                for (const c of r)await a.execute(s, c);
            } finally{
                await s.close();
            }
            e + n < o.length && await new Promise((c)=>setTimeout(c, 0));
        }
    };
    Be = async ()=>{
        a || await A();
        try {
            const t = new Array(384).fill(0).map((T, d)=>d / 384);
            let o = null;
            for (const T of N)try {
                const R = await (await a.query(`MATCH (n:${T}) RETURN n.id AS id LIMIT 1`)).getNext();
                if (R) {
                    o = R.id ?? R[0];
                    break;
                }
            } catch  {}
            if (!o) return {
                success: !1,
                error: "No nodes found to test with"
            };
            const n = `CREATE (e:${L} {nodeId: $nodeId, embedding: $embedding})`, e = await a.prepare(n);
            if (!e.isSuccess()) return {
                success: !1,
                error: `Prepare failed: ${await e.getErrorMessage()}`
            };
            await a.execute(e, {
                nodeId: o,
                embedding: t
            }), await e.close();
            const s = await (await a.query(`MATCH (e:${L} {nodeId: '${o}'}) RETURN e.embedding AS emb`)).getNext(), c = s?.emb ?? s?.[0];
            return c && Array.isArray(c) && c.length === 384 ? {
                success: !0
            } : {
                success: !1,
                error: `Embedding not stored correctly. Got: ${typeof c}, length: ${c?.length}`
            };
        } catch (t) {
            return {
                success: !1,
                error: t instanceof Error ? t.message : String(t)
            };
        }
    };
})();
export { Ge as closeKuzu, He as executePrepared, _e as executeQuery, De as executeWithReusedStatement, $e as getKuzuStats, A as initKuzu, be as isKuzuReady, Le as loadGraphToKuzu, Be as testArrayParams, __tla };
