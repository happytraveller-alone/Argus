(async () => {
  (function() {
    const t = document.createElement("link").relList;
    if (t && t.supports && t.supports("modulepreload")) return;
    for (const i of document.querySelectorAll('link[rel="modulepreload"]')) r(i);
    new MutationObserver((i) => {
      for (const o of i) if (o.type === "childList") for (const s of o.addedNodes) s.tagName === "LINK" && s.rel === "modulepreload" && r(s);
    }).observe(document, {
      childList: true,
      subtree: true
    });
    function n(i) {
      const o = {};
      return i.integrity && (o.integrity = i.integrity), i.referrerPolicy && (o.referrerPolicy = i.referrerPolicy), i.crossOrigin === "use-credentials" ? o.credentials = "include" : i.crossOrigin === "anonymous" ? o.credentials = "omit" : o.credentials = "same-origin", o;
    }
    function r(i) {
      if (i.ep) return;
      i.ep = true;
      const o = n(i);
      fetch(i.href, o);
    }
  })();
  function To(e) {
    return e && e.__esModule && Object.prototype.hasOwnProperty.call(e, "default") ? e.default : e;
  }
  var Tf = {
    exports: {}
  }, ta = {}, Rf = {
    exports: {}
  }, Ee = {};
  var Ro = Symbol.for("react.element"), Em = Symbol.for("react.portal"), Sm = Symbol.for("react.fragment"), _m = Symbol.for("react.strict_mode"), km = Symbol.for("react.profiler"), bm = Symbol.for("react.provider"), xm = Symbol.for("react.context"), Cm = Symbol.for("react.forward_ref"), Tm = Symbol.for("react.suspense"), Rm = Symbol.for("react.memo"), Am = Symbol.for("react.lazy"), bc = Symbol.iterator;
  function Lm(e) {
    return e === null || typeof e != "object" ? null : (e = bc && e[bc] || e["@@iterator"], typeof e == "function" ? e : null);
  }
  var Af = {
    isMounted: function() {
      return false;
    },
    enqueueForceUpdate: function() {
    },
    enqueueReplaceState: function() {
    },
    enqueueSetState: function() {
    }
  }, Lf = Object.assign, If = {};
  function wi(e, t, n) {
    this.props = e, this.context = t, this.refs = If, this.updater = n || Af;
  }
  wi.prototype.isReactComponent = {};
  wi.prototype.setState = function(e, t) {
    if (typeof e != "object" && typeof e != "function" && e != null) throw Error("setState(...): takes an object of state variables to update or a function which returns an object of state variables.");
    this.updater.enqueueSetState(this, e, t, "setState");
  };
  wi.prototype.forceUpdate = function(e) {
    this.updater.enqueueForceUpdate(this, e, "forceUpdate");
  };
  function Df() {
  }
  Df.prototype = wi.prototype;
  function vu(e, t, n) {
    this.props = e, this.context = t, this.refs = If, this.updater = n || Af;
  }
  var yu = vu.prototype = new Df();
  yu.constructor = vu;
  Lf(yu, wi.prototype);
  yu.isPureReactComponent = true;
  var xc = Array.isArray, Pf = Object.prototype.hasOwnProperty, wu = {
    current: null
  }, Nf = {
    key: true,
    ref: true,
    __self: true,
    __source: true
  };
  function Ff(e, t, n) {
    var r, i = {}, o = null, s = null;
    if (t != null) for (r in t.ref !== void 0 && (s = t.ref), t.key !== void 0 && (o = "" + t.key), t) Pf.call(t, r) && !Nf.hasOwnProperty(r) && (i[r] = t[r]);
    var a = arguments.length - 2;
    if (a === 1) i.children = n;
    else if (1 < a) {
      for (var l = Array(a), c = 0; c < a; c++) l[c] = arguments[c + 2];
      i.children = l;
    }
    if (e && e.defaultProps) for (r in a = e.defaultProps, a) i[r] === void 0 && (i[r] = a[r]);
    return {
      $$typeof: Ro,
      type: e,
      key: o,
      ref: s,
      props: i,
      _owner: wu.current
    };
  }
  function Im(e, t) {
    return {
      $$typeof: Ro,
      type: e.type,
      key: t,
      ref: e.ref,
      props: e.props,
      _owner: e._owner
    };
  }
  function Eu(e) {
    return typeof e == "object" && e !== null && e.$$typeof === Ro;
  }
  function Dm(e) {
    var t = {
      "=": "=0",
      ":": "=2"
    };
    return "$" + e.replace(/[=:]/g, function(n) {
      return t[n];
    });
  }
  var Cc = /\/+/g;
  function Ca(e, t) {
    return typeof e == "object" && e !== null && e.key != null ? Dm("" + e.key) : t.toString(36);
  }
  function us(e, t, n, r, i) {
    var o = typeof e;
    (o === "undefined" || o === "boolean") && (e = null);
    var s = false;
    if (e === null) s = true;
    else switch (o) {
      case "string":
      case "number":
        s = true;
        break;
      case "object":
        switch (e.$$typeof) {
          case Ro:
          case Em:
            s = true;
        }
    }
    if (s) return s = e, i = i(s), e = r === "" ? "." + Ca(s, 0) : r, xc(i) ? (n = "", e != null && (n = e.replace(Cc, "$&/") + "/"), us(i, t, n, "", function(c) {
      return c;
    })) : i != null && (Eu(i) && (i = Im(i, n + (!i.key || s && s.key === i.key ? "" : ("" + i.key).replace(Cc, "$&/") + "/") + e)), t.push(i)), 1;
    if (s = 0, r = r === "" ? "." : r + ":", xc(e)) for (var a = 0; a < e.length; a++) {
      o = e[a];
      var l = r + Ca(o, a);
      s += us(o, t, n, l, i);
    }
    else if (l = Lm(e), typeof l == "function") for (e = l.call(e), a = 0; !(o = e.next()).done; ) o = o.value, l = r + Ca(o, a++), s += us(o, t, n, l, i);
    else if (o === "object") throw t = String(e), Error("Objects are not valid as a React child (found: " + (t === "[object Object]" ? "object with keys {" + Object.keys(e).join(", ") + "}" : t) + "). If you meant to render a collection of children, use an array instead.");
    return s;
  }
  function Oo(e, t, n) {
    if (e == null) return e;
    var r = [], i = 0;
    return us(e, r, "", "", function(o) {
      return t.call(n, o, i++);
    }), r;
  }
  function Pm(e) {
    if (e._status === -1) {
      var t = e._result;
      t = t(), t.then(function(n) {
        (e._status === 0 || e._status === -1) && (e._status = 1, e._result = n);
      }, function(n) {
        (e._status === 0 || e._status === -1) && (e._status = 2, e._result = n);
      }), e._status === -1 && (e._status = 0, e._result = t);
    }
    if (e._status === 1) return e._result.default;
    throw e._result;
  }
  var It = {
    current: null
  }, cs = {
    transition: null
  }, Nm = {
    ReactCurrentDispatcher: It,
    ReactCurrentBatchConfig: cs,
    ReactCurrentOwner: wu
  };
  function zf() {
    throw Error("act(...) is not supported in production builds of React.");
  }
  Ee.Children = {
    map: Oo,
    forEach: function(e, t, n) {
      Oo(e, function() {
        t.apply(this, arguments);
      }, n);
    },
    count: function(e) {
      var t = 0;
      return Oo(e, function() {
        t++;
      }), t;
    },
    toArray: function(e) {
      return Oo(e, function(t) {
        return t;
      }) || [];
    },
    only: function(e) {
      if (!Eu(e)) throw Error("React.Children.only expected to receive a single React element child.");
      return e;
    }
  };
  Ee.Component = wi;
  Ee.Fragment = Sm;
  Ee.Profiler = km;
  Ee.PureComponent = vu;
  Ee.StrictMode = _m;
  Ee.Suspense = Tm;
  Ee.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED = Nm;
  Ee.act = zf;
  Ee.cloneElement = function(e, t, n) {
    if (e == null) throw Error("React.cloneElement(...): The argument must be a React element, but you passed " + e + ".");
    var r = Lf({}, e.props), i = e.key, o = e.ref, s = e._owner;
    if (t != null) {
      if (t.ref !== void 0 && (o = t.ref, s = wu.current), t.key !== void 0 && (i = "" + t.key), e.type && e.type.defaultProps) var a = e.type.defaultProps;
      for (l in t) Pf.call(t, l) && !Nf.hasOwnProperty(l) && (r[l] = t[l] === void 0 && a !== void 0 ? a[l] : t[l]);
    }
    var l = arguments.length - 2;
    if (l === 1) r.children = n;
    else if (1 < l) {
      a = Array(l);
      for (var c = 0; c < l; c++) a[c] = arguments[c + 2];
      r.children = a;
    }
    return {
      $$typeof: Ro,
      type: e.type,
      key: i,
      ref: o,
      props: r,
      _owner: s
    };
  };
  Ee.createContext = function(e) {
    return e = {
      $$typeof: xm,
      _currentValue: e,
      _currentValue2: e,
      _threadCount: 0,
      Provider: null,
      Consumer: null,
      _defaultValue: null,
      _globalName: null
    }, e.Provider = {
      $$typeof: bm,
      _context: e
    }, e.Consumer = e;
  };
  Ee.createElement = Ff;
  Ee.createFactory = function(e) {
    var t = Ff.bind(null, e);
    return t.type = e, t;
  };
  Ee.createRef = function() {
    return {
      current: null
    };
  };
  Ee.forwardRef = function(e) {
    return {
      $$typeof: Cm,
      render: e
    };
  };
  Ee.isValidElement = Eu;
  Ee.lazy = function(e) {
    return {
      $$typeof: Am,
      _payload: {
        _status: -1,
        _result: e
      },
      _init: Pm
    };
  };
  Ee.memo = function(e, t) {
    return {
      $$typeof: Rm,
      type: e,
      compare: t === void 0 ? null : t
    };
  };
  Ee.startTransition = function(e) {
    var t = cs.transition;
    cs.transition = {};
    try {
      e();
    } finally {
      cs.transition = t;
    }
  };
  Ee.unstable_act = zf;
  Ee.useCallback = function(e, t) {
    return It.current.useCallback(e, t);
  };
  Ee.useContext = function(e) {
    return It.current.useContext(e);
  };
  Ee.useDebugValue = function() {
  };
  Ee.useDeferredValue = function(e) {
    return It.current.useDeferredValue(e);
  };
  Ee.useEffect = function(e, t) {
    return It.current.useEffect(e, t);
  };
  Ee.useId = function() {
    return It.current.useId();
  };
  Ee.useImperativeHandle = function(e, t, n) {
    return It.current.useImperativeHandle(e, t, n);
  };
  Ee.useInsertionEffect = function(e, t) {
    return It.current.useInsertionEffect(e, t);
  };
  Ee.useLayoutEffect = function(e, t) {
    return It.current.useLayoutEffect(e, t);
  };
  Ee.useMemo = function(e, t) {
    return It.current.useMemo(e, t);
  };
  Ee.useReducer = function(e, t, n) {
    return It.current.useReducer(e, t, n);
  };
  Ee.useRef = function(e) {
    return It.current.useRef(e);
  };
  Ee.useState = function(e) {
    return It.current.useState(e);
  };
  Ee.useSyncExternalStore = function(e, t, n) {
    return It.current.useSyncExternalStore(e, t, n);
  };
  Ee.useTransition = function() {
    return It.current.useTransition();
  };
  Ee.version = "18.3.1";
  Rf.exports = Ee;
  var z = Rf.exports;
  const Fm = To(z);
  var zm = z, Om = Symbol.for("react.element"), Gm = Symbol.for("react.fragment"), Um = Object.prototype.hasOwnProperty, Bm = zm.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentOwner, Mm = {
    key: true,
    ref: true,
    __self: true,
    __source: true
  };
  function Of(e, t, n) {
    var r, i = {}, o = null, s = null;
    n !== void 0 && (o = "" + n), t.key !== void 0 && (o = "" + t.key), t.ref !== void 0 && (s = t.ref);
    for (r in t) Um.call(t, r) && !Mm.hasOwnProperty(r) && (i[r] = t[r]);
    if (e && e.defaultProps) for (r in t = e.defaultProps, t) i[r] === void 0 && (i[r] = t[r]);
    return {
      $$typeof: Om,
      type: e,
      key: o,
      ref: s,
      props: i,
      _owner: Bm.current
    };
  }
  ta.Fragment = Gm;
  ta.jsx = Of;
  ta.jsxs = Of;
  Tf.exports = ta;
  var M = Tf.exports, pl = {}, Gf = {
    exports: {}
  }, Kt = {}, Uf = {
    exports: {}
  }, Bf = {};
  (function(e) {
    function t(S, j) {
      var H = S.length;
      S.push(j);
      e: for (; 0 < H; ) {
        var D = H - 1 >>> 1, x = S[D];
        if (0 < i(x, j)) S[D] = j, S[H] = x, H = D;
        else break e;
      }
    }
    function n(S) {
      return S.length === 0 ? null : S[0];
    }
    function r(S) {
      if (S.length === 0) return null;
      var j = S[0], H = S.pop();
      if (H !== j) {
        S[0] = H;
        e: for (var D = 0, x = S.length, Q = x >>> 1; D < Q; ) {
          var ie = 2 * (D + 1) - 1, _e = S[ie], Se = ie + 1, oe = S[Se];
          if (0 > i(_e, H)) Se < x && 0 > i(oe, _e) ? (S[D] = oe, S[Se] = H, D = Se) : (S[D] = _e, S[ie] = H, D = ie);
          else if (Se < x && 0 > i(oe, H)) S[D] = oe, S[Se] = H, D = Se;
          else break e;
        }
      }
      return j;
    }
    function i(S, j) {
      var H = S.sortIndex - j.sortIndex;
      return H !== 0 ? H : S.id - j.id;
    }
    if (typeof performance == "object" && typeof performance.now == "function") {
      var o = performance;
      e.unstable_now = function() {
        return o.now();
      };
    } else {
      var s = Date, a = s.now();
      e.unstable_now = function() {
        return s.now() - a;
      };
    }
    var l = [], c = [], h = 1, f = null, p = 3, y = false, k = false, b = false, I = typeof setTimeout == "function" ? setTimeout : null, _ = typeof clearTimeout == "function" ? clearTimeout : null, m = typeof setImmediate < "u" ? setImmediate : null;
    typeof navigator < "u" && navigator.scheduling !== void 0 && navigator.scheduling.isInputPending !== void 0 && navigator.scheduling.isInputPending.bind(navigator.scheduling);
    function v(S) {
      for (var j = n(c); j !== null; ) {
        if (j.callback === null) r(c);
        else if (j.startTime <= S) r(c), j.sortIndex = j.expirationTime, t(l, j);
        else break;
        j = n(c);
      }
    }
    function E(S) {
      if (b = false, v(S), !k) if (n(l) !== null) k = true, ae(A);
      else {
        var j = n(c);
        j !== null && J(E, j.startTime - S);
      }
    }
    function A(S, j) {
      k = false, b && (b = false, _(L), L = -1), y = true;
      var H = p;
      try {
        for (v(j), f = n(l); f !== null && (!(f.expirationTime > j) || S && !V()); ) {
          var D = f.callback;
          if (typeof D == "function") {
            f.callback = null, p = f.priorityLevel;
            var x = D(f.expirationTime <= j);
            j = e.unstable_now(), typeof x == "function" ? f.callback = x : f === n(l) && r(l), v(j);
          } else r(l);
          f = n(l);
        }
        if (f !== null) var Q = true;
        else {
          var ie = n(c);
          ie !== null && J(E, ie.startTime - j), Q = false;
        }
        return Q;
      } finally {
        f = null, p = H, y = false;
      }
    }
    var F = false, R = null, L = -1, C = 5, N = -1;
    function V() {
      return !(e.unstable_now() - N < C);
    }
    function B() {
      if (R !== null) {
        var S = e.unstable_now();
        N = S;
        var j = true;
        try {
          j = R(true, S);
        } finally {
          j ? K() : (F = false, R = null);
        }
      } else F = false;
    }
    var K;
    if (typeof m == "function") K = function() {
      m(B);
    };
    else if (typeof MessageChannel < "u") {
      var O = new MessageChannel(), re = O.port2;
      O.port1.onmessage = B, K = function() {
        re.postMessage(null);
      };
    } else K = function() {
      I(B, 0);
    };
    function ae(S) {
      R = S, F || (F = true, K());
    }
    function J(S, j) {
      L = I(function() {
        S(e.unstable_now());
      }, j);
    }
    e.unstable_IdlePriority = 5, e.unstable_ImmediatePriority = 1, e.unstable_LowPriority = 4, e.unstable_NormalPriority = 3, e.unstable_Profiling = null, e.unstable_UserBlockingPriority = 2, e.unstable_cancelCallback = function(S) {
      S.callback = null;
    }, e.unstable_continueExecution = function() {
      k || y || (k = true, ae(A));
    }, e.unstable_forceFrameRate = function(S) {
      0 > S || 125 < S ? console.error("forceFrameRate takes a positive int between 0 and 125, forcing frame rates higher than 125 fps is not supported") : C = 0 < S ? Math.floor(1e3 / S) : 5;
    }, e.unstable_getCurrentPriorityLevel = function() {
      return p;
    }, e.unstable_getFirstCallbackNode = function() {
      return n(l);
    }, e.unstable_next = function(S) {
      switch (p) {
        case 1:
        case 2:
        case 3:
          var j = 3;
          break;
        default:
          j = p;
      }
      var H = p;
      p = j;
      try {
        return S();
      } finally {
        p = H;
      }
    }, e.unstable_pauseExecution = function() {
    }, e.unstable_requestPaint = function() {
    }, e.unstable_runWithPriority = function(S, j) {
      switch (S) {
        case 1:
        case 2:
        case 3:
        case 4:
        case 5:
          break;
        default:
          S = 3;
      }
      var H = p;
      p = S;
      try {
        return j();
      } finally {
        p = H;
      }
    }, e.unstable_scheduleCallback = function(S, j, H) {
      var D = e.unstable_now();
      switch (typeof H == "object" && H !== null ? (H = H.delay, H = typeof H == "number" && 0 < H ? D + H : D) : H = D, S) {
        case 1:
          var x = -1;
          break;
        case 2:
          x = 250;
          break;
        case 5:
          x = 1073741823;
          break;
        case 4:
          x = 1e4;
          break;
        default:
          x = 5e3;
      }
      return x = H + x, S = {
        id: h++,
        callback: j,
        priorityLevel: S,
        startTime: H,
        expirationTime: x,
        sortIndex: -1
      }, H > D ? (S.sortIndex = H, t(c, S), n(l) === null && S === n(c) && (b ? (_(L), L = -1) : b = true, J(E, H - D))) : (S.sortIndex = x, t(l, S), k || y || (k = true, ae(A))), S;
    }, e.unstable_shouldYield = V, e.unstable_wrapCallback = function(S) {
      var j = p;
      return function() {
        var H = p;
        p = j;
        try {
          return S.apply(this, arguments);
        } finally {
          p = H;
        }
      };
    };
  })(Bf);
  Uf.exports = Bf;
  var $m = Uf.exports;
  var jm = z, Vt = $m;
  function W(e) {
    for (var t = "https://reactjs.org/docs/error-decoder.html?invariant=" + e, n = 1; n < arguments.length; n++) t += "&args[]=" + encodeURIComponent(arguments[n]);
    return "Minified React error #" + e + "; visit " + t + " for the full message or use the non-minified dev environment for full errors and additional helpful warnings.";
  }
  var Mf = /* @__PURE__ */ new Set(), lo = {};
  function Or(e, t) {
    ui(e, t), ui(e + "Capture", t);
  }
  function ui(e, t) {
    for (lo[e] = t, e = 0; e < t.length; e++) Mf.add(t[e]);
  }
  var Hn = !(typeof window > "u" || typeof window.document > "u" || typeof window.document.createElement > "u"), gl = Object.prototype.hasOwnProperty, Hm = /^[:A-Z_a-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD][:A-Z_a-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD\-.0-9\u00B7\u0300-\u036F\u203F-\u2040]*$/, Tc = {}, Rc = {};
  function Wm(e) {
    return gl.call(Rc, e) ? true : gl.call(Tc, e) ? false : Hm.test(e) ? Rc[e] = true : (Tc[e] = true, false);
  }
  function Vm(e, t, n, r) {
    if (n !== null && n.type === 0) return false;
    switch (typeof t) {
      case "function":
      case "symbol":
        return true;
      case "boolean":
        return r ? false : n !== null ? !n.acceptsBooleans : (e = e.toLowerCase().slice(0, 5), e !== "data-" && e !== "aria-");
      default:
        return false;
    }
  }
  function Km(e, t, n, r) {
    if (t === null || typeof t > "u" || Vm(e, t, n, r)) return true;
    if (r) return false;
    if (n !== null) switch (n.type) {
      case 3:
        return !t;
      case 4:
        return t === false;
      case 5:
        return isNaN(t);
      case 6:
        return isNaN(t) || 1 > t;
    }
    return false;
  }
  function Dt(e, t, n, r, i, o, s) {
    this.acceptsBooleans = t === 2 || t === 3 || t === 4, this.attributeName = r, this.attributeNamespace = i, this.mustUseProperty = n, this.propertyName = e, this.type = t, this.sanitizeURL = o, this.removeEmptyString = s;
  }
  var gt = {};
  "children dangerouslySetInnerHTML defaultValue defaultChecked innerHTML suppressContentEditableWarning suppressHydrationWarning style".split(" ").forEach(function(e) {
    gt[e] = new Dt(e, 0, false, e, null, false, false);
  });
  [
    [
      "acceptCharset",
      "accept-charset"
    ],
    [
      "className",
      "class"
    ],
    [
      "htmlFor",
      "for"
    ],
    [
      "httpEquiv",
      "http-equiv"
    ]
  ].forEach(function(e) {
    var t = e[0];
    gt[t] = new Dt(t, 1, false, e[1], null, false, false);
  });
  [
    "contentEditable",
    "draggable",
    "spellCheck",
    "value"
  ].forEach(function(e) {
    gt[e] = new Dt(e, 2, false, e.toLowerCase(), null, false, false);
  });
  [
    "autoReverse",
    "externalResourcesRequired",
    "focusable",
    "preserveAlpha"
  ].forEach(function(e) {
    gt[e] = new Dt(e, 2, false, e, null, false, false);
  });
  "allowFullScreen async autoFocus autoPlay controls default defer disabled disablePictureInPicture disableRemotePlayback formNoValidate hidden loop noModule noValidate open playsInline readOnly required reversed scoped seamless itemScope".split(" ").forEach(function(e) {
    gt[e] = new Dt(e, 3, false, e.toLowerCase(), null, false, false);
  });
  [
    "checked",
    "multiple",
    "muted",
    "selected"
  ].forEach(function(e) {
    gt[e] = new Dt(e, 3, true, e, null, false, false);
  });
  [
    "capture",
    "download"
  ].forEach(function(e) {
    gt[e] = new Dt(e, 4, false, e, null, false, false);
  });
  [
    "cols",
    "rows",
    "size",
    "span"
  ].forEach(function(e) {
    gt[e] = new Dt(e, 6, false, e, null, false, false);
  });
  [
    "rowSpan",
    "start"
  ].forEach(function(e) {
    gt[e] = new Dt(e, 5, false, e.toLowerCase(), null, false, false);
  });
  var Su = /[\-:]([a-z])/g;
  function _u(e) {
    return e[1].toUpperCase();
  }
  "accent-height alignment-baseline arabic-form baseline-shift cap-height clip-path clip-rule color-interpolation color-interpolation-filters color-profile color-rendering dominant-baseline enable-background fill-opacity fill-rule flood-color flood-opacity font-family font-size font-size-adjust font-stretch font-style font-variant font-weight glyph-name glyph-orientation-horizontal glyph-orientation-vertical horiz-adv-x horiz-origin-x image-rendering letter-spacing lighting-color marker-end marker-mid marker-start overline-position overline-thickness paint-order panose-1 pointer-events rendering-intent shape-rendering stop-color stop-opacity strikethrough-position strikethrough-thickness stroke-dasharray stroke-dashoffset stroke-linecap stroke-linejoin stroke-miterlimit stroke-opacity stroke-width text-anchor text-decoration text-rendering underline-position underline-thickness unicode-bidi unicode-range units-per-em v-alphabetic v-hanging v-ideographic v-mathematical vector-effect vert-adv-y vert-origin-x vert-origin-y word-spacing writing-mode xmlns:xlink x-height".split(" ").forEach(function(e) {
    var t = e.replace(Su, _u);
    gt[t] = new Dt(t, 1, false, e, null, false, false);
  });
  "xlink:actuate xlink:arcrole xlink:role xlink:show xlink:title xlink:type".split(" ").forEach(function(e) {
    var t = e.replace(Su, _u);
    gt[t] = new Dt(t, 1, false, e, "http://www.w3.org/1999/xlink", false, false);
  });
  [
    "xml:base",
    "xml:lang",
    "xml:space"
  ].forEach(function(e) {
    var t = e.replace(Su, _u);
    gt[t] = new Dt(t, 1, false, e, "http://www.w3.org/XML/1998/namespace", false, false);
  });
  [
    "tabIndex",
    "crossOrigin"
  ].forEach(function(e) {
    gt[e] = new Dt(e, 1, false, e.toLowerCase(), null, false, false);
  });
  gt.xlinkHref = new Dt("xlinkHref", 1, false, "xlink:href", "http://www.w3.org/1999/xlink", true, false);
  [
    "src",
    "href",
    "action",
    "formAction"
  ].forEach(function(e) {
    gt[e] = new Dt(e, 1, false, e.toLowerCase(), null, true, true);
  });
  function ku(e, t, n, r) {
    var i = gt.hasOwnProperty(t) ? gt[t] : null;
    (i !== null ? i.type !== 0 : r || !(2 < t.length) || t[0] !== "o" && t[0] !== "O" || t[1] !== "n" && t[1] !== "N") && (Km(t, n, i, r) && (n = null), r || i === null ? Wm(t) && (n === null ? e.removeAttribute(t) : e.setAttribute(t, "" + n)) : i.mustUseProperty ? e[i.propertyName] = n === null ? i.type === 3 ? false : "" : n : (t = i.attributeName, r = i.attributeNamespace, n === null ? e.removeAttribute(t) : (i = i.type, n = i === 3 || i === 4 && n === true ? "" : "" + n, r ? e.setAttributeNS(r, t, n) : e.setAttribute(t, n))));
  }
  var Yn = jm.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED, Go = Symbol.for("react.element"), jr = Symbol.for("react.portal"), Hr = Symbol.for("react.fragment"), bu = Symbol.for("react.strict_mode"), ml = Symbol.for("react.profiler"), $f = Symbol.for("react.provider"), jf = Symbol.for("react.context"), xu = Symbol.for("react.forward_ref"), vl = Symbol.for("react.suspense"), yl = Symbol.for("react.suspense_list"), Cu = Symbol.for("react.memo"), nr = Symbol.for("react.lazy"), Hf = Symbol.for("react.offscreen"), Ac = Symbol.iterator;
  function Ai(e) {
    return e === null || typeof e != "object" ? null : (e = Ac && e[Ac] || e["@@iterator"], typeof e == "function" ? e : null);
  }
  var je = Object.assign, Ta;
  function Ki(e) {
    if (Ta === void 0) try {
      throw Error();
    } catch (n) {
      var t = n.stack.trim().match(/\n( *(at )?)/);
      Ta = t && t[1] || "";
    }
    return `
` + Ta + e;
  }
  var Ra = false;
  function Aa(e, t) {
    if (!e || Ra) return "";
    Ra = true;
    var n = Error.prepareStackTrace;
    Error.prepareStackTrace = void 0;
    try {
      if (t) if (t = function() {
        throw Error();
      }, Object.defineProperty(t.prototype, "props", {
        set: function() {
          throw Error();
        }
      }), typeof Reflect == "object" && Reflect.construct) {
        try {
          Reflect.construct(t, []);
        } catch (c) {
          var r = c;
        }
        Reflect.construct(e, [], t);
      } else {
        try {
          t.call();
        } catch (c) {
          r = c;
        }
        e.call(t.prototype);
      }
      else {
        try {
          throw Error();
        } catch (c) {
          r = c;
        }
        e();
      }
    } catch (c) {
      if (c && r && typeof c.stack == "string") {
        for (var i = c.stack.split(`
`), o = r.stack.split(`
`), s = i.length - 1, a = o.length - 1; 1 <= s && 0 <= a && i[s] !== o[a]; ) a--;
        for (; 1 <= s && 0 <= a; s--, a--) if (i[s] !== o[a]) {
          if (s !== 1 || a !== 1) do
            if (s--, a--, 0 > a || i[s] !== o[a]) {
              var l = `
` + i[s].replace(" at new ", " at ");
              return e.displayName && l.includes("<anonymous>") && (l = l.replace("<anonymous>", e.displayName)), l;
            }
          while (1 <= s && 0 <= a);
          break;
        }
      }
    } finally {
      Ra = false, Error.prepareStackTrace = n;
    }
    return (e = e ? e.displayName || e.name : "") ? Ki(e) : "";
  }
  function Ym(e) {
    switch (e.tag) {
      case 5:
        return Ki(e.type);
      case 16:
        return Ki("Lazy");
      case 13:
        return Ki("Suspense");
      case 19:
        return Ki("SuspenseList");
      case 0:
      case 2:
      case 15:
        return e = Aa(e.type, false), e;
      case 11:
        return e = Aa(e.type.render, false), e;
      case 1:
        return e = Aa(e.type, true), e;
      default:
        return "";
    }
  }
  function wl(e) {
    if (e == null) return null;
    if (typeof e == "function") return e.displayName || e.name || null;
    if (typeof e == "string") return e;
    switch (e) {
      case Hr:
        return "Fragment";
      case jr:
        return "Portal";
      case ml:
        return "Profiler";
      case bu:
        return "StrictMode";
      case vl:
        return "Suspense";
      case yl:
        return "SuspenseList";
    }
    if (typeof e == "object") switch (e.$$typeof) {
      case jf:
        return (e.displayName || "Context") + ".Consumer";
      case $f:
        return (e._context.displayName || "Context") + ".Provider";
      case xu:
        var t = e.render;
        return e = e.displayName, e || (e = t.displayName || t.name || "", e = e !== "" ? "ForwardRef(" + e + ")" : "ForwardRef"), e;
      case Cu:
        return t = e.displayName || null, t !== null ? t : wl(e.type) || "Memo";
      case nr:
        t = e._payload, e = e._init;
        try {
          return wl(e(t));
        } catch {
        }
    }
    return null;
  }
  function Qm(e) {
    var t = e.type;
    switch (e.tag) {
      case 24:
        return "Cache";
      case 9:
        return (t.displayName || "Context") + ".Consumer";
      case 10:
        return (t._context.displayName || "Context") + ".Provider";
      case 18:
        return "DehydratedFragment";
      case 11:
        return e = t.render, e = e.displayName || e.name || "", t.displayName || (e !== "" ? "ForwardRef(" + e + ")" : "ForwardRef");
      case 7:
        return "Fragment";
      case 5:
        return t;
      case 4:
        return "Portal";
      case 3:
        return "Root";
      case 6:
        return "Text";
      case 16:
        return wl(t);
      case 8:
        return t === bu ? "StrictMode" : "Mode";
      case 22:
        return "Offscreen";
      case 12:
        return "Profiler";
      case 21:
        return "Scope";
      case 13:
        return "Suspense";
      case 19:
        return "SuspenseList";
      case 25:
        return "TracingMarker";
      case 1:
      case 0:
      case 17:
      case 2:
      case 14:
      case 15:
        if (typeof t == "function") return t.displayName || t.name || null;
        if (typeof t == "string") return t;
    }
    return null;
  }
  function mr(e) {
    switch (typeof e) {
      case "boolean":
      case "number":
      case "string":
      case "undefined":
        return e;
      case "object":
        return e;
      default:
        return "";
    }
  }
  function Wf(e) {
    var t = e.type;
    return (e = e.nodeName) && e.toLowerCase() === "input" && (t === "checkbox" || t === "radio");
  }
  function Xm(e) {
    var t = Wf(e) ? "checked" : "value", n = Object.getOwnPropertyDescriptor(e.constructor.prototype, t), r = "" + e[t];
    if (!e.hasOwnProperty(t) && typeof n < "u" && typeof n.get == "function" && typeof n.set == "function") {
      var i = n.get, o = n.set;
      return Object.defineProperty(e, t, {
        configurable: true,
        get: function() {
          return i.call(this);
        },
        set: function(s) {
          r = "" + s, o.call(this, s);
        }
      }), Object.defineProperty(e, t, {
        enumerable: n.enumerable
      }), {
        getValue: function() {
          return r;
        },
        setValue: function(s) {
          r = "" + s;
        },
        stopTracking: function() {
          e._valueTracker = null, delete e[t];
        }
      };
    }
  }
  function Uo(e) {
    e._valueTracker || (e._valueTracker = Xm(e));
  }
  function Vf(e) {
    if (!e) return false;
    var t = e._valueTracker;
    if (!t) return true;
    var n = t.getValue(), r = "";
    return e && (r = Wf(e) ? e.checked ? "true" : "false" : e.value), e = r, e !== n ? (t.setValue(e), true) : false;
  }
  function bs(e) {
    if (e = e || (typeof document < "u" ? document : void 0), typeof e > "u") return null;
    try {
      return e.activeElement || e.body;
    } catch {
      return e.body;
    }
  }
  function El(e, t) {
    var n = t.checked;
    return je({}, t, {
      defaultChecked: void 0,
      defaultValue: void 0,
      value: void 0,
      checked: n ?? e._wrapperState.initialChecked
    });
  }
  function Lc(e, t) {
    var n = t.defaultValue == null ? "" : t.defaultValue, r = t.checked != null ? t.checked : t.defaultChecked;
    n = mr(t.value != null ? t.value : n), e._wrapperState = {
      initialChecked: r,
      initialValue: n,
      controlled: t.type === "checkbox" || t.type === "radio" ? t.checked != null : t.value != null
    };
  }
  function Kf(e, t) {
    t = t.checked, t != null && ku(e, "checked", t, false);
  }
  function Sl(e, t) {
    Kf(e, t);
    var n = mr(t.value), r = t.type;
    if (n != null) r === "number" ? (n === 0 && e.value === "" || e.value != n) && (e.value = "" + n) : e.value !== "" + n && (e.value = "" + n);
    else if (r === "submit" || r === "reset") {
      e.removeAttribute("value");
      return;
    }
    t.hasOwnProperty("value") ? _l(e, t.type, n) : t.hasOwnProperty("defaultValue") && _l(e, t.type, mr(t.defaultValue)), t.checked == null && t.defaultChecked != null && (e.defaultChecked = !!t.defaultChecked);
  }
  function Ic(e, t, n) {
    if (t.hasOwnProperty("value") || t.hasOwnProperty("defaultValue")) {
      var r = t.type;
      if (!(r !== "submit" && r !== "reset" || t.value !== void 0 && t.value !== null)) return;
      t = "" + e._wrapperState.initialValue, n || t === e.value || (e.value = t), e.defaultValue = t;
    }
    n = e.name, n !== "" && (e.name = ""), e.defaultChecked = !!e._wrapperState.initialChecked, n !== "" && (e.name = n);
  }
  function _l(e, t, n) {
    (t !== "number" || bs(e.ownerDocument) !== e) && (n == null ? e.defaultValue = "" + e._wrapperState.initialValue : e.defaultValue !== "" + n && (e.defaultValue = "" + n));
  }
  var Yi = Array.isArray;
  function ti(e, t, n, r) {
    if (e = e.options, t) {
      t = {};
      for (var i = 0; i < n.length; i++) t["$" + n[i]] = true;
      for (n = 0; n < e.length; n++) i = t.hasOwnProperty("$" + e[n].value), e[n].selected !== i && (e[n].selected = i), i && r && (e[n].defaultSelected = true);
    } else {
      for (n = "" + mr(n), t = null, i = 0; i < e.length; i++) {
        if (e[i].value === n) {
          e[i].selected = true, r && (e[i].defaultSelected = true);
          return;
        }
        t !== null || e[i].disabled || (t = e[i]);
      }
      t !== null && (t.selected = true);
    }
  }
  function kl(e, t) {
    if (t.dangerouslySetInnerHTML != null) throw Error(W(91));
    return je({}, t, {
      value: void 0,
      defaultValue: void 0,
      children: "" + e._wrapperState.initialValue
    });
  }
  function Dc(e, t) {
    var n = t.value;
    if (n == null) {
      if (n = t.children, t = t.defaultValue, n != null) {
        if (t != null) throw Error(W(92));
        if (Yi(n)) {
          if (1 < n.length) throw Error(W(93));
          n = n[0];
        }
        t = n;
      }
      t == null && (t = ""), n = t;
    }
    e._wrapperState = {
      initialValue: mr(n)
    };
  }
  function Yf(e, t) {
    var n = mr(t.value), r = mr(t.defaultValue);
    n != null && (n = "" + n, n !== e.value && (e.value = n), t.defaultValue == null && e.defaultValue !== n && (e.defaultValue = n)), r != null && (e.defaultValue = "" + r);
  }
  function Pc(e) {
    var t = e.textContent;
    t === e._wrapperState.initialValue && t !== "" && t !== null && (e.value = t);
  }
  function Qf(e) {
    switch (e) {
      case "svg":
        return "http://www.w3.org/2000/svg";
      case "math":
        return "http://www.w3.org/1998/Math/MathML";
      default:
        return "http://www.w3.org/1999/xhtml";
    }
  }
  function bl(e, t) {
    return e == null || e === "http://www.w3.org/1999/xhtml" ? Qf(t) : e === "http://www.w3.org/2000/svg" && t === "foreignObject" ? "http://www.w3.org/1999/xhtml" : e;
  }
  var Bo, Xf = function(e) {
    return typeof MSApp < "u" && MSApp.execUnsafeLocalFunction ? function(t, n, r, i) {
      MSApp.execUnsafeLocalFunction(function() {
        return e(t, n, r, i);
      });
    } : e;
  }(function(e, t) {
    if (e.namespaceURI !== "http://www.w3.org/2000/svg" || "innerHTML" in e) e.innerHTML = t;
    else {
      for (Bo = Bo || document.createElement("div"), Bo.innerHTML = "<svg>" + t.valueOf().toString() + "</svg>", t = Bo.firstChild; e.firstChild; ) e.removeChild(e.firstChild);
      for (; t.firstChild; ) e.appendChild(t.firstChild);
    }
  });
  function uo(e, t) {
    if (t) {
      var n = e.firstChild;
      if (n && n === e.lastChild && n.nodeType === 3) {
        n.nodeValue = t;
        return;
      }
    }
    e.textContent = t;
  }
  var qi = {
    animationIterationCount: true,
    aspectRatio: true,
    borderImageOutset: true,
    borderImageSlice: true,
    borderImageWidth: true,
    boxFlex: true,
    boxFlexGroup: true,
    boxOrdinalGroup: true,
    columnCount: true,
    columns: true,
    flex: true,
    flexGrow: true,
    flexPositive: true,
    flexShrink: true,
    flexNegative: true,
    flexOrder: true,
    gridArea: true,
    gridRow: true,
    gridRowEnd: true,
    gridRowSpan: true,
    gridRowStart: true,
    gridColumn: true,
    gridColumnEnd: true,
    gridColumnSpan: true,
    gridColumnStart: true,
    fontWeight: true,
    lineClamp: true,
    lineHeight: true,
    opacity: true,
    order: true,
    orphans: true,
    tabSize: true,
    widows: true,
    zIndex: true,
    zoom: true,
    fillOpacity: true,
    floodOpacity: true,
    stopOpacity: true,
    strokeDasharray: true,
    strokeDashoffset: true,
    strokeMiterlimit: true,
    strokeOpacity: true,
    strokeWidth: true
  }, Zm = [
    "Webkit",
    "ms",
    "Moz",
    "O"
  ];
  Object.keys(qi).forEach(function(e) {
    Zm.forEach(function(t) {
      t = t + e.charAt(0).toUpperCase() + e.substring(1), qi[t] = qi[e];
    });
  });
  function Zf(e, t, n) {
    return t == null || typeof t == "boolean" || t === "" ? "" : n || typeof t != "number" || t === 0 || qi.hasOwnProperty(e) && qi[e] ? ("" + t).trim() : t + "px";
  }
  function qf(e, t) {
    e = e.style;
    for (var n in t) if (t.hasOwnProperty(n)) {
      var r = n.indexOf("--") === 0, i = Zf(n, t[n], r);
      n === "float" && (n = "cssFloat"), r ? e.setProperty(n, i) : e[n] = i;
    }
  }
  var qm = je({
    menuitem: true
  }, {
    area: true,
    base: true,
    br: true,
    col: true,
    embed: true,
    hr: true,
    img: true,
    input: true,
    keygen: true,
    link: true,
    meta: true,
    param: true,
    source: true,
    track: true,
    wbr: true
  });
  function xl(e, t) {
    if (t) {
      if (qm[e] && (t.children != null || t.dangerouslySetInnerHTML != null)) throw Error(W(137, e));
      if (t.dangerouslySetInnerHTML != null) {
        if (t.children != null) throw Error(W(60));
        if (typeof t.dangerouslySetInnerHTML != "object" || !("__html" in t.dangerouslySetInnerHTML)) throw Error(W(61));
      }
      if (t.style != null && typeof t.style != "object") throw Error(W(62));
    }
  }
  function Cl(e, t) {
    if (e.indexOf("-") === -1) return typeof t.is == "string";
    switch (e) {
      case "annotation-xml":
      case "color-profile":
      case "font-face":
      case "font-face-src":
      case "font-face-uri":
      case "font-face-format":
      case "font-face-name":
      case "missing-glyph":
        return false;
      default:
        return true;
    }
  }
  var Tl = null;
  function Tu(e) {
    return e = e.target || e.srcElement || window, e.correspondingUseElement && (e = e.correspondingUseElement), e.nodeType === 3 ? e.parentNode : e;
  }
  var Rl = null, ni = null, ri = null;
  function Nc(e) {
    if (e = Io(e)) {
      if (typeof Rl != "function") throw Error(W(280));
      var t = e.stateNode;
      t && (t = sa(t), Rl(e.stateNode, e.type, t));
    }
  }
  function Jf(e) {
    ni ? ri ? ri.push(e) : ri = [
      e
    ] : ni = e;
  }
  function eh() {
    if (ni) {
      var e = ni, t = ri;
      if (ri = ni = null, Nc(e), t) for (e = 0; e < t.length; e++) Nc(t[e]);
    }
  }
  function th(e, t) {
    return e(t);
  }
  function nh() {
  }
  var La = false;
  function rh(e, t, n) {
    if (La) return e(t, n);
    La = true;
    try {
      return th(e, t, n);
    } finally {
      La = false, (ni !== null || ri !== null) && (nh(), eh());
    }
  }
  function co(e, t) {
    var n = e.stateNode;
    if (n === null) return null;
    var r = sa(n);
    if (r === null) return null;
    n = r[t];
    e: switch (t) {
      case "onClick":
      case "onClickCapture":
      case "onDoubleClick":
      case "onDoubleClickCapture":
      case "onMouseDown":
      case "onMouseDownCapture":
      case "onMouseMove":
      case "onMouseMoveCapture":
      case "onMouseUp":
      case "onMouseUpCapture":
      case "onMouseEnter":
        (r = !r.disabled) || (e = e.type, r = !(e === "button" || e === "input" || e === "select" || e === "textarea")), e = !r;
        break e;
      default:
        e = false;
    }
    if (e) return null;
    if (n && typeof n != "function") throw Error(W(231, t, typeof n));
    return n;
  }
  var Al = false;
  if (Hn) try {
    var Li = {};
    Object.defineProperty(Li, "passive", {
      get: function() {
        Al = true;
      }
    }), window.addEventListener("test", Li, Li), window.removeEventListener("test", Li, Li);
  } catch {
    Al = false;
  }
  function Jm(e, t, n, r, i, o, s, a, l) {
    var c = Array.prototype.slice.call(arguments, 3);
    try {
      t.apply(n, c);
    } catch (h) {
      this.onError(h);
    }
  }
  var Ji = false, xs = null, Cs = false, Ll = null, ev = {
    onError: function(e) {
      Ji = true, xs = e;
    }
  };
  function tv(e, t, n, r, i, o, s, a, l) {
    Ji = false, xs = null, Jm.apply(ev, arguments);
  }
  function nv(e, t, n, r, i, o, s, a, l) {
    if (tv.apply(this, arguments), Ji) {
      if (Ji) {
        var c = xs;
        Ji = false, xs = null;
      } else throw Error(W(198));
      Cs || (Cs = true, Ll = c);
    }
  }
  function Gr(e) {
    var t = e, n = e;
    if (e.alternate) for (; t.return; ) t = t.return;
    else {
      e = t;
      do
        t = e, t.flags & 4098 && (n = t.return), e = t.return;
      while (e);
    }
    return t.tag === 3 ? n : null;
  }
  function ih(e) {
    if (e.tag === 13) {
      var t = e.memoizedState;
      if (t === null && (e = e.alternate, e !== null && (t = e.memoizedState)), t !== null) return t.dehydrated;
    }
    return null;
  }
  function Fc(e) {
    if (Gr(e) !== e) throw Error(W(188));
  }
  function rv(e) {
    var t = e.alternate;
    if (!t) {
      if (t = Gr(e), t === null) throw Error(W(188));
      return t !== e ? null : e;
    }
    for (var n = e, r = t; ; ) {
      var i = n.return;
      if (i === null) break;
      var o = i.alternate;
      if (o === null) {
        if (r = i.return, r !== null) {
          n = r;
          continue;
        }
        break;
      }
      if (i.child === o.child) {
        for (o = i.child; o; ) {
          if (o === n) return Fc(i), e;
          if (o === r) return Fc(i), t;
          o = o.sibling;
        }
        throw Error(W(188));
      }
      if (n.return !== r.return) n = i, r = o;
      else {
        for (var s = false, a = i.child; a; ) {
          if (a === n) {
            s = true, n = i, r = o;
            break;
          }
          if (a === r) {
            s = true, r = i, n = o;
            break;
          }
          a = a.sibling;
        }
        if (!s) {
          for (a = o.child; a; ) {
            if (a === n) {
              s = true, n = o, r = i;
              break;
            }
            if (a === r) {
              s = true, r = o, n = i;
              break;
            }
            a = a.sibling;
          }
          if (!s) throw Error(W(189));
        }
      }
      if (n.alternate !== r) throw Error(W(190));
    }
    if (n.tag !== 3) throw Error(W(188));
    return n.stateNode.current === n ? e : t;
  }
  function oh(e) {
    return e = rv(e), e !== null ? sh(e) : null;
  }
  function sh(e) {
    if (e.tag === 5 || e.tag === 6) return e;
    for (e = e.child; e !== null; ) {
      var t = sh(e);
      if (t !== null) return t;
      e = e.sibling;
    }
    return null;
  }
  var ah = Vt.unstable_scheduleCallback, zc = Vt.unstable_cancelCallback, iv = Vt.unstable_shouldYield, ov = Vt.unstable_requestPaint, Ze = Vt.unstable_now, sv = Vt.unstable_getCurrentPriorityLevel, Ru = Vt.unstable_ImmediatePriority, lh = Vt.unstable_UserBlockingPriority, Ts = Vt.unstable_NormalPriority, av = Vt.unstable_LowPriority, uh = Vt.unstable_IdlePriority, na = null, An = null;
  function lv(e) {
    if (An && typeof An.onCommitFiberRoot == "function") try {
      An.onCommitFiberRoot(na, e, void 0, (e.current.flags & 128) === 128);
    } catch {
    }
  }
  var wn = Math.clz32 ? Math.clz32 : dv, uv = Math.log, cv = Math.LN2;
  function dv(e) {
    return e >>>= 0, e === 0 ? 32 : 31 - (uv(e) / cv | 0) | 0;
  }
  var Mo = 64, $o = 4194304;
  function Qi(e) {
    switch (e & -e) {
      case 1:
        return 1;
      case 2:
        return 2;
      case 4:
        return 4;
      case 8:
        return 8;
      case 16:
        return 16;
      case 32:
        return 32;
      case 64:
      case 128:
      case 256:
      case 512:
      case 1024:
      case 2048:
      case 4096:
      case 8192:
      case 16384:
      case 32768:
      case 65536:
      case 131072:
      case 262144:
      case 524288:
      case 1048576:
      case 2097152:
        return e & 4194240;
      case 4194304:
      case 8388608:
      case 16777216:
      case 33554432:
      case 67108864:
        return e & 130023424;
      case 134217728:
        return 134217728;
      case 268435456:
        return 268435456;
      case 536870912:
        return 536870912;
      case 1073741824:
        return 1073741824;
      default:
        return e;
    }
  }
  function Rs(e, t) {
    var n = e.pendingLanes;
    if (n === 0) return 0;
    var r = 0, i = e.suspendedLanes, o = e.pingedLanes, s = n & 268435455;
    if (s !== 0) {
      var a = s & ~i;
      a !== 0 ? r = Qi(a) : (o &= s, o !== 0 && (r = Qi(o)));
    } else s = n & ~i, s !== 0 ? r = Qi(s) : o !== 0 && (r = Qi(o));
    if (r === 0) return 0;
    if (t !== 0 && t !== r && !(t & i) && (i = r & -r, o = t & -t, i >= o || i === 16 && (o & 4194240) !== 0)) return t;
    if (r & 4 && (r |= n & 16), t = e.entangledLanes, t !== 0) for (e = e.entanglements, t &= r; 0 < t; ) n = 31 - wn(t), i = 1 << n, r |= e[n], t &= ~i;
    return r;
  }
  function fv(e, t) {
    switch (e) {
      case 1:
      case 2:
      case 4:
        return t + 250;
      case 8:
      case 16:
      case 32:
      case 64:
      case 128:
      case 256:
      case 512:
      case 1024:
      case 2048:
      case 4096:
      case 8192:
      case 16384:
      case 32768:
      case 65536:
      case 131072:
      case 262144:
      case 524288:
      case 1048576:
      case 2097152:
        return t + 5e3;
      case 4194304:
      case 8388608:
      case 16777216:
      case 33554432:
      case 67108864:
        return -1;
      case 134217728:
      case 268435456:
      case 536870912:
      case 1073741824:
        return -1;
      default:
        return -1;
    }
  }
  function hv(e, t) {
    for (var n = e.suspendedLanes, r = e.pingedLanes, i = e.expirationTimes, o = e.pendingLanes; 0 < o; ) {
      var s = 31 - wn(o), a = 1 << s, l = i[s];
      l === -1 ? (!(a & n) || a & r) && (i[s] = fv(a, t)) : l <= t && (e.expiredLanes |= a), o &= ~a;
    }
  }
  function Il(e) {
    return e = e.pendingLanes & -1073741825, e !== 0 ? e : e & 1073741824 ? 1073741824 : 0;
  }
  function ch() {
    var e = Mo;
    return Mo <<= 1, !(Mo & 4194240) && (Mo = 64), e;
  }
  function Ia(e) {
    for (var t = [], n = 0; 31 > n; n++) t.push(e);
    return t;
  }
  function Ao(e, t, n) {
    e.pendingLanes |= t, t !== 536870912 && (e.suspendedLanes = 0, e.pingedLanes = 0), e = e.eventTimes, t = 31 - wn(t), e[t] = n;
  }
  function pv(e, t) {
    var n = e.pendingLanes & ~t;
    e.pendingLanes = t, e.suspendedLanes = 0, e.pingedLanes = 0, e.expiredLanes &= t, e.mutableReadLanes &= t, e.entangledLanes &= t, t = e.entanglements;
    var r = e.eventTimes;
    for (e = e.expirationTimes; 0 < n; ) {
      var i = 31 - wn(n), o = 1 << i;
      t[i] = 0, r[i] = -1, e[i] = -1, n &= ~o;
    }
  }
  function Au(e, t) {
    var n = e.entangledLanes |= t;
    for (e = e.entanglements; n; ) {
      var r = 31 - wn(n), i = 1 << r;
      i & t | e[r] & t && (e[r] |= t), n &= ~i;
    }
  }
  var De = 0;
  function dh(e) {
    return e &= -e, 1 < e ? 4 < e ? e & 268435455 ? 16 : 536870912 : 4 : 1;
  }
  var fh, Lu, hh, ph, gh, Dl = false, jo = [], lr = null, ur = null, cr = null, fo = /* @__PURE__ */ new Map(), ho = /* @__PURE__ */ new Map(), ir = [], gv = "mousedown mouseup touchcancel touchend touchstart auxclick dblclick pointercancel pointerdown pointerup dragend dragstart drop compositionend compositionstart keydown keypress keyup input textInput copy cut paste click change contextmenu reset submit".split(" ");
  function Oc(e, t) {
    switch (e) {
      case "focusin":
      case "focusout":
        lr = null;
        break;
      case "dragenter":
      case "dragleave":
        ur = null;
        break;
      case "mouseover":
      case "mouseout":
        cr = null;
        break;
      case "pointerover":
      case "pointerout":
        fo.delete(t.pointerId);
        break;
      case "gotpointercapture":
      case "lostpointercapture":
        ho.delete(t.pointerId);
    }
  }
  function Ii(e, t, n, r, i, o) {
    return e === null || e.nativeEvent !== o ? (e = {
      blockedOn: t,
      domEventName: n,
      eventSystemFlags: r,
      nativeEvent: o,
      targetContainers: [
        i
      ]
    }, t !== null && (t = Io(t), t !== null && Lu(t)), e) : (e.eventSystemFlags |= r, t = e.targetContainers, i !== null && t.indexOf(i) === -1 && t.push(i), e);
  }
  function mv(e, t, n, r, i) {
    switch (t) {
      case "focusin":
        return lr = Ii(lr, e, t, n, r, i), true;
      case "dragenter":
        return ur = Ii(ur, e, t, n, r, i), true;
      case "mouseover":
        return cr = Ii(cr, e, t, n, r, i), true;
      case "pointerover":
        var o = i.pointerId;
        return fo.set(o, Ii(fo.get(o) || null, e, t, n, r, i)), true;
      case "gotpointercapture":
        return o = i.pointerId, ho.set(o, Ii(ho.get(o) || null, e, t, n, r, i)), true;
    }
    return false;
  }
  function mh(e) {
    var t = Tr(e.target);
    if (t !== null) {
      var n = Gr(t);
      if (n !== null) {
        if (t = n.tag, t === 13) {
          if (t = ih(n), t !== null) {
            e.blockedOn = t, gh(e.priority, function() {
              hh(n);
            });
            return;
          }
        } else if (t === 3 && n.stateNode.current.memoizedState.isDehydrated) {
          e.blockedOn = n.tag === 3 ? n.stateNode.containerInfo : null;
          return;
        }
      }
    }
    e.blockedOn = null;
  }
  function ds(e) {
    if (e.blockedOn !== null) return false;
    for (var t = e.targetContainers; 0 < t.length; ) {
      var n = Pl(e.domEventName, e.eventSystemFlags, t[0], e.nativeEvent);
      if (n === null) {
        n = e.nativeEvent;
        var r = new n.constructor(n.type, n);
        Tl = r, n.target.dispatchEvent(r), Tl = null;
      } else return t = Io(n), t !== null && Lu(t), e.blockedOn = n, false;
      t.shift();
    }
    return true;
  }
  function Gc(e, t, n) {
    ds(e) && n.delete(t);
  }
  function vv() {
    Dl = false, lr !== null && ds(lr) && (lr = null), ur !== null && ds(ur) && (ur = null), cr !== null && ds(cr) && (cr = null), fo.forEach(Gc), ho.forEach(Gc);
  }
  function Di(e, t) {
    e.blockedOn === t && (e.blockedOn = null, Dl || (Dl = true, Vt.unstable_scheduleCallback(Vt.unstable_NormalPriority, vv)));
  }
  function po(e) {
    function t(i) {
      return Di(i, e);
    }
    if (0 < jo.length) {
      Di(jo[0], e);
      for (var n = 1; n < jo.length; n++) {
        var r = jo[n];
        r.blockedOn === e && (r.blockedOn = null);
      }
    }
    for (lr !== null && Di(lr, e), ur !== null && Di(ur, e), cr !== null && Di(cr, e), fo.forEach(t), ho.forEach(t), n = 0; n < ir.length; n++) r = ir[n], r.blockedOn === e && (r.blockedOn = null);
    for (; 0 < ir.length && (n = ir[0], n.blockedOn === null); ) mh(n), n.blockedOn === null && ir.shift();
  }
  var ii = Yn.ReactCurrentBatchConfig, As = true;
  function yv(e, t, n, r) {
    var i = De, o = ii.transition;
    ii.transition = null;
    try {
      De = 1, Iu(e, t, n, r);
    } finally {
      De = i, ii.transition = o;
    }
  }
  function wv(e, t, n, r) {
    var i = De, o = ii.transition;
    ii.transition = null;
    try {
      De = 4, Iu(e, t, n, r);
    } finally {
      De = i, ii.transition = o;
    }
  }
  function Iu(e, t, n, r) {
    if (As) {
      var i = Pl(e, t, n, r);
      if (i === null) Ma(e, t, r, Ls, n), Oc(e, r);
      else if (mv(i, e, t, n, r)) r.stopPropagation();
      else if (Oc(e, r), t & 4 && -1 < gv.indexOf(e)) {
        for (; i !== null; ) {
          var o = Io(i);
          if (o !== null && fh(o), o = Pl(e, t, n, r), o === null && Ma(e, t, r, Ls, n), o === i) break;
          i = o;
        }
        i !== null && r.stopPropagation();
      } else Ma(e, t, r, null, n);
    }
  }
  var Ls = null;
  function Pl(e, t, n, r) {
    if (Ls = null, e = Tu(r), e = Tr(e), e !== null) if (t = Gr(e), t === null) e = null;
    else if (n = t.tag, n === 13) {
      if (e = ih(t), e !== null) return e;
      e = null;
    } else if (n === 3) {
      if (t.stateNode.current.memoizedState.isDehydrated) return t.tag === 3 ? t.stateNode.containerInfo : null;
      e = null;
    } else t !== e && (e = null);
    return Ls = e, null;
  }
  function vh(e) {
    switch (e) {
      case "cancel":
      case "click":
      case "close":
      case "contextmenu":
      case "copy":
      case "cut":
      case "auxclick":
      case "dblclick":
      case "dragend":
      case "dragstart":
      case "drop":
      case "focusin":
      case "focusout":
      case "input":
      case "invalid":
      case "keydown":
      case "keypress":
      case "keyup":
      case "mousedown":
      case "mouseup":
      case "paste":
      case "pause":
      case "play":
      case "pointercancel":
      case "pointerdown":
      case "pointerup":
      case "ratechange":
      case "reset":
      case "resize":
      case "seeked":
      case "submit":
      case "touchcancel":
      case "touchend":
      case "touchstart":
      case "volumechange":
      case "change":
      case "selectionchange":
      case "textInput":
      case "compositionstart":
      case "compositionend":
      case "compositionupdate":
      case "beforeblur":
      case "afterblur":
      case "beforeinput":
      case "blur":
      case "fullscreenchange":
      case "focus":
      case "hashchange":
      case "popstate":
      case "select":
      case "selectstart":
        return 1;
      case "drag":
      case "dragenter":
      case "dragexit":
      case "dragleave":
      case "dragover":
      case "mousemove":
      case "mouseout":
      case "mouseover":
      case "pointermove":
      case "pointerout":
      case "pointerover":
      case "scroll":
      case "toggle":
      case "touchmove":
      case "wheel":
      case "mouseenter":
      case "mouseleave":
      case "pointerenter":
      case "pointerleave":
        return 4;
      case "message":
        switch (sv()) {
          case Ru:
            return 1;
          case lh:
            return 4;
          case Ts:
          case av:
            return 16;
          case uh:
            return 536870912;
          default:
            return 16;
        }
      default:
        return 16;
    }
  }
  var sr = null, Du = null, fs = null;
  function yh() {
    if (fs) return fs;
    var e, t = Du, n = t.length, r, i = "value" in sr ? sr.value : sr.textContent, o = i.length;
    for (e = 0; e < n && t[e] === i[e]; e++) ;
    var s = n - e;
    for (r = 1; r <= s && t[n - r] === i[o - r]; r++) ;
    return fs = i.slice(e, 1 < r ? 1 - r : void 0);
  }
  function hs(e) {
    var t = e.keyCode;
    return "charCode" in e ? (e = e.charCode, e === 0 && t === 13 && (e = 13)) : e = t, e === 10 && (e = 13), 32 <= e || e === 13 ? e : 0;
  }
  function Ho() {
    return true;
  }
  function Uc() {
    return false;
  }
  function Yt(e) {
    function t(n, r, i, o, s) {
      this._reactName = n, this._targetInst = i, this.type = r, this.nativeEvent = o, this.target = s, this.currentTarget = null;
      for (var a in e) e.hasOwnProperty(a) && (n = e[a], this[a] = n ? n(o) : o[a]);
      return this.isDefaultPrevented = (o.defaultPrevented != null ? o.defaultPrevented : o.returnValue === false) ? Ho : Uc, this.isPropagationStopped = Uc, this;
    }
    return je(t.prototype, {
      preventDefault: function() {
        this.defaultPrevented = true;
        var n = this.nativeEvent;
        n && (n.preventDefault ? n.preventDefault() : typeof n.returnValue != "unknown" && (n.returnValue = false), this.isDefaultPrevented = Ho);
      },
      stopPropagation: function() {
        var n = this.nativeEvent;
        n && (n.stopPropagation ? n.stopPropagation() : typeof n.cancelBubble != "unknown" && (n.cancelBubble = true), this.isPropagationStopped = Ho);
      },
      persist: function() {
      },
      isPersistent: Ho
    }), t;
  }
  var Ei = {
    eventPhase: 0,
    bubbles: 0,
    cancelable: 0,
    timeStamp: function(e) {
      return e.timeStamp || Date.now();
    },
    defaultPrevented: 0,
    isTrusted: 0
  }, Pu = Yt(Ei), Lo = je({}, Ei, {
    view: 0,
    detail: 0
  }), Ev = Yt(Lo), Da, Pa, Pi, ra = je({}, Lo, {
    screenX: 0,
    screenY: 0,
    clientX: 0,
    clientY: 0,
    pageX: 0,
    pageY: 0,
    ctrlKey: 0,
    shiftKey: 0,
    altKey: 0,
    metaKey: 0,
    getModifierState: Nu,
    button: 0,
    buttons: 0,
    relatedTarget: function(e) {
      return e.relatedTarget === void 0 ? e.fromElement === e.srcElement ? e.toElement : e.fromElement : e.relatedTarget;
    },
    movementX: function(e) {
      return "movementX" in e ? e.movementX : (e !== Pi && (Pi && e.type === "mousemove" ? (Da = e.screenX - Pi.screenX, Pa = e.screenY - Pi.screenY) : Pa = Da = 0, Pi = e), Da);
    },
    movementY: function(e) {
      return "movementY" in e ? e.movementY : Pa;
    }
  }), Bc = Yt(ra), Sv = je({}, ra, {
    dataTransfer: 0
  }), _v = Yt(Sv), kv = je({}, Lo, {
    relatedTarget: 0
  }), Na = Yt(kv), bv = je({}, Ei, {
    animationName: 0,
    elapsedTime: 0,
    pseudoElement: 0
  }), xv = Yt(bv), Cv = je({}, Ei, {
    clipboardData: function(e) {
      return "clipboardData" in e ? e.clipboardData : window.clipboardData;
    }
  }), Tv = Yt(Cv), Rv = je({}, Ei, {
    data: 0
  }), Mc = Yt(Rv), Av = {
    Esc: "Escape",
    Spacebar: " ",
    Left: "ArrowLeft",
    Up: "ArrowUp",
    Right: "ArrowRight",
    Down: "ArrowDown",
    Del: "Delete",
    Win: "OS",
    Menu: "ContextMenu",
    Apps: "ContextMenu",
    Scroll: "ScrollLock",
    MozPrintableKey: "Unidentified"
  }, Lv = {
    8: "Backspace",
    9: "Tab",
    12: "Clear",
    13: "Enter",
    16: "Shift",
    17: "Control",
    18: "Alt",
    19: "Pause",
    20: "CapsLock",
    27: "Escape",
    32: " ",
    33: "PageUp",
    34: "PageDown",
    35: "End",
    36: "Home",
    37: "ArrowLeft",
    38: "ArrowUp",
    39: "ArrowRight",
    40: "ArrowDown",
    45: "Insert",
    46: "Delete",
    112: "F1",
    113: "F2",
    114: "F3",
    115: "F4",
    116: "F5",
    117: "F6",
    118: "F7",
    119: "F8",
    120: "F9",
    121: "F10",
    122: "F11",
    123: "F12",
    144: "NumLock",
    145: "ScrollLock",
    224: "Meta"
  }, Iv = {
    Alt: "altKey",
    Control: "ctrlKey",
    Meta: "metaKey",
    Shift: "shiftKey"
  };
  function Dv(e) {
    var t = this.nativeEvent;
    return t.getModifierState ? t.getModifierState(e) : (e = Iv[e]) ? !!t[e] : false;
  }
  function Nu() {
    return Dv;
  }
  var Pv = je({}, Lo, {
    key: function(e) {
      if (e.key) {
        var t = Av[e.key] || e.key;
        if (t !== "Unidentified") return t;
      }
      return e.type === "keypress" ? (e = hs(e), e === 13 ? "Enter" : String.fromCharCode(e)) : e.type === "keydown" || e.type === "keyup" ? Lv[e.keyCode] || "Unidentified" : "";
    },
    code: 0,
    location: 0,
    ctrlKey: 0,
    shiftKey: 0,
    altKey: 0,
    metaKey: 0,
    repeat: 0,
    locale: 0,
    getModifierState: Nu,
    charCode: function(e) {
      return e.type === "keypress" ? hs(e) : 0;
    },
    keyCode: function(e) {
      return e.type === "keydown" || e.type === "keyup" ? e.keyCode : 0;
    },
    which: function(e) {
      return e.type === "keypress" ? hs(e) : e.type === "keydown" || e.type === "keyup" ? e.keyCode : 0;
    }
  }), Nv = Yt(Pv), Fv = je({}, ra, {
    pointerId: 0,
    width: 0,
    height: 0,
    pressure: 0,
    tangentialPressure: 0,
    tiltX: 0,
    tiltY: 0,
    twist: 0,
    pointerType: 0,
    isPrimary: 0
  }), $c = Yt(Fv), zv = je({}, Lo, {
    touches: 0,
    targetTouches: 0,
    changedTouches: 0,
    altKey: 0,
    metaKey: 0,
    ctrlKey: 0,
    shiftKey: 0,
    getModifierState: Nu
  }), Ov = Yt(zv), Gv = je({}, Ei, {
    propertyName: 0,
    elapsedTime: 0,
    pseudoElement: 0
  }), Uv = Yt(Gv), Bv = je({}, ra, {
    deltaX: function(e) {
      return "deltaX" in e ? e.deltaX : "wheelDeltaX" in e ? -e.wheelDeltaX : 0;
    },
    deltaY: function(e) {
      return "deltaY" in e ? e.deltaY : "wheelDeltaY" in e ? -e.wheelDeltaY : "wheelDelta" in e ? -e.wheelDelta : 0;
    },
    deltaZ: 0,
    deltaMode: 0
  }), Mv = Yt(Bv), $v = [
    9,
    13,
    27,
    32
  ], Fu = Hn && "CompositionEvent" in window, eo = null;
  Hn && "documentMode" in document && (eo = document.documentMode);
  var jv = Hn && "TextEvent" in window && !eo, wh = Hn && (!Fu || eo && 8 < eo && 11 >= eo), jc = " ", Hc = false;
  function Eh(e, t) {
    switch (e) {
      case "keyup":
        return $v.indexOf(t.keyCode) !== -1;
      case "keydown":
        return t.keyCode !== 229;
      case "keypress":
      case "mousedown":
      case "focusout":
        return true;
      default:
        return false;
    }
  }
  function Sh(e) {
    return e = e.detail, typeof e == "object" && "data" in e ? e.data : null;
  }
  var Wr = false;
  function Hv(e, t) {
    switch (e) {
      case "compositionend":
        return Sh(t);
      case "keypress":
        return t.which !== 32 ? null : (Hc = true, jc);
      case "textInput":
        return e = t.data, e === jc && Hc ? null : e;
      default:
        return null;
    }
  }
  function Wv(e, t) {
    if (Wr) return e === "compositionend" || !Fu && Eh(e, t) ? (e = yh(), fs = Du = sr = null, Wr = false, e) : null;
    switch (e) {
      case "paste":
        return null;
      case "keypress":
        if (!(t.ctrlKey || t.altKey || t.metaKey) || t.ctrlKey && t.altKey) {
          if (t.char && 1 < t.char.length) return t.char;
          if (t.which) return String.fromCharCode(t.which);
        }
        return null;
      case "compositionend":
        return wh && t.locale !== "ko" ? null : t.data;
      default:
        return null;
    }
  }
  var Vv = {
    color: true,
    date: true,
    datetime: true,
    "datetime-local": true,
    email: true,
    month: true,
    number: true,
    password: true,
    range: true,
    search: true,
    tel: true,
    text: true,
    time: true,
    url: true,
    week: true
  };
  function Wc(e) {
    var t = e && e.nodeName && e.nodeName.toLowerCase();
    return t === "input" ? !!Vv[e.type] : t === "textarea";
  }
  function _h(e, t, n, r) {
    Jf(r), t = Is(t, "onChange"), 0 < t.length && (n = new Pu("onChange", "change", null, n, r), e.push({
      event: n,
      listeners: t
    }));
  }
  var to = null, go = null;
  function Kv(e) {
    Ph(e, 0);
  }
  function ia(e) {
    var t = Yr(e);
    if (Vf(t)) return e;
  }
  function Yv(e, t) {
    if (e === "change") return t;
  }
  var kh = false;
  if (Hn) {
    var Fa;
    if (Hn) {
      var za = "oninput" in document;
      if (!za) {
        var Vc = document.createElement("div");
        Vc.setAttribute("oninput", "return;"), za = typeof Vc.oninput == "function";
      }
      Fa = za;
    } else Fa = false;
    kh = Fa && (!document.documentMode || 9 < document.documentMode);
  }
  function Kc() {
    to && (to.detachEvent("onpropertychange", bh), go = to = null);
  }
  function bh(e) {
    if (e.propertyName === "value" && ia(go)) {
      var t = [];
      _h(t, go, e, Tu(e)), rh(Kv, t);
    }
  }
  function Qv(e, t, n) {
    e === "focusin" ? (Kc(), to = t, go = n, to.attachEvent("onpropertychange", bh)) : e === "focusout" && Kc();
  }
  function Xv(e) {
    if (e === "selectionchange" || e === "keyup" || e === "keydown") return ia(go);
  }
  function Zv(e, t) {
    if (e === "click") return ia(t);
  }
  function qv(e, t) {
    if (e === "input" || e === "change") return ia(t);
  }
  function Jv(e, t) {
    return e === t && (e !== 0 || 1 / e === 1 / t) || e !== e && t !== t;
  }
  var Sn = typeof Object.is == "function" ? Object.is : Jv;
  function mo(e, t) {
    if (Sn(e, t)) return true;
    if (typeof e != "object" || e === null || typeof t != "object" || t === null) return false;
    var n = Object.keys(e), r = Object.keys(t);
    if (n.length !== r.length) return false;
    for (r = 0; r < n.length; r++) {
      var i = n[r];
      if (!gl.call(t, i) || !Sn(e[i], t[i])) return false;
    }
    return true;
  }
  function Yc(e) {
    for (; e && e.firstChild; ) e = e.firstChild;
    return e;
  }
  function Qc(e, t) {
    var n = Yc(e);
    e = 0;
    for (var r; n; ) {
      if (n.nodeType === 3) {
        if (r = e + n.textContent.length, e <= t && r >= t) return {
          node: n,
          offset: t - e
        };
        e = r;
      }
      e: {
        for (; n; ) {
          if (n.nextSibling) {
            n = n.nextSibling;
            break e;
          }
          n = n.parentNode;
        }
        n = void 0;
      }
      n = Yc(n);
    }
  }
  function xh(e, t) {
    return e && t ? e === t ? true : e && e.nodeType === 3 ? false : t && t.nodeType === 3 ? xh(e, t.parentNode) : "contains" in e ? e.contains(t) : e.compareDocumentPosition ? !!(e.compareDocumentPosition(t) & 16) : false : false;
  }
  function Ch() {
    for (var e = window, t = bs(); t instanceof e.HTMLIFrameElement; ) {
      try {
        var n = typeof t.contentWindow.location.href == "string";
      } catch {
        n = false;
      }
      if (n) e = t.contentWindow;
      else break;
      t = bs(e.document);
    }
    return t;
  }
  function zu(e) {
    var t = e && e.nodeName && e.nodeName.toLowerCase();
    return t && (t === "input" && (e.type === "text" || e.type === "search" || e.type === "tel" || e.type === "url" || e.type === "password") || t === "textarea" || e.contentEditable === "true");
  }
  function ey(e) {
    var t = Ch(), n = e.focusedElem, r = e.selectionRange;
    if (t !== n && n && n.ownerDocument && xh(n.ownerDocument.documentElement, n)) {
      if (r !== null && zu(n)) {
        if (t = r.start, e = r.end, e === void 0 && (e = t), "selectionStart" in n) n.selectionStart = t, n.selectionEnd = Math.min(e, n.value.length);
        else if (e = (t = n.ownerDocument || document) && t.defaultView || window, e.getSelection) {
          e = e.getSelection();
          var i = n.textContent.length, o = Math.min(r.start, i);
          r = r.end === void 0 ? o : Math.min(r.end, i), !e.extend && o > r && (i = r, r = o, o = i), i = Qc(n, o);
          var s = Qc(n, r);
          i && s && (e.rangeCount !== 1 || e.anchorNode !== i.node || e.anchorOffset !== i.offset || e.focusNode !== s.node || e.focusOffset !== s.offset) && (t = t.createRange(), t.setStart(i.node, i.offset), e.removeAllRanges(), o > r ? (e.addRange(t), e.extend(s.node, s.offset)) : (t.setEnd(s.node, s.offset), e.addRange(t)));
        }
      }
      for (t = [], e = n; e = e.parentNode; ) e.nodeType === 1 && t.push({
        element: e,
        left: e.scrollLeft,
        top: e.scrollTop
      });
      for (typeof n.focus == "function" && n.focus(), n = 0; n < t.length; n++) e = t[n], e.element.scrollLeft = e.left, e.element.scrollTop = e.top;
    }
  }
  var ty = Hn && "documentMode" in document && 11 >= document.documentMode, Vr = null, Nl = null, no = null, Fl = false;
  function Xc(e, t, n) {
    var r = n.window === n ? n.document : n.nodeType === 9 ? n : n.ownerDocument;
    Fl || Vr == null || Vr !== bs(r) || (r = Vr, "selectionStart" in r && zu(r) ? r = {
      start: r.selectionStart,
      end: r.selectionEnd
    } : (r = (r.ownerDocument && r.ownerDocument.defaultView || window).getSelection(), r = {
      anchorNode: r.anchorNode,
      anchorOffset: r.anchorOffset,
      focusNode: r.focusNode,
      focusOffset: r.focusOffset
    }), no && mo(no, r) || (no = r, r = Is(Nl, "onSelect"), 0 < r.length && (t = new Pu("onSelect", "select", null, t, n), e.push({
      event: t,
      listeners: r
    }), t.target = Vr)));
  }
  function Wo(e, t) {
    var n = {};
    return n[e.toLowerCase()] = t.toLowerCase(), n["Webkit" + e] = "webkit" + t, n["Moz" + e] = "moz" + t, n;
  }
  var Kr = {
    animationend: Wo("Animation", "AnimationEnd"),
    animationiteration: Wo("Animation", "AnimationIteration"),
    animationstart: Wo("Animation", "AnimationStart"),
    transitionend: Wo("Transition", "TransitionEnd")
  }, Oa = {}, Th = {};
  Hn && (Th = document.createElement("div").style, "AnimationEvent" in window || (delete Kr.animationend.animation, delete Kr.animationiteration.animation, delete Kr.animationstart.animation), "TransitionEvent" in window || delete Kr.transitionend.transition);
  function oa(e) {
    if (Oa[e]) return Oa[e];
    if (!Kr[e]) return e;
    var t = Kr[e], n;
    for (n in t) if (t.hasOwnProperty(n) && n in Th) return Oa[e] = t[n];
    return e;
  }
  var Rh = oa("animationend"), Ah = oa("animationiteration"), Lh = oa("animationstart"), Ih = oa("transitionend"), Dh = /* @__PURE__ */ new Map(), Zc = "abort auxClick cancel canPlay canPlayThrough click close contextMenu copy cut drag dragEnd dragEnter dragExit dragLeave dragOver dragStart drop durationChange emptied encrypted ended error gotPointerCapture input invalid keyDown keyPress keyUp load loadedData loadedMetadata loadStart lostPointerCapture mouseDown mouseMove mouseOut mouseOver mouseUp paste pause play playing pointerCancel pointerDown pointerMove pointerOut pointerOver pointerUp progress rateChange reset resize seeked seeking stalled submit suspend timeUpdate touchCancel touchEnd touchStart volumeChange scroll toggle touchMove waiting wheel".split(" ");
  function yr(e, t) {
    Dh.set(e, t), Or(t, [
      e
    ]);
  }
  for (var Ga = 0; Ga < Zc.length; Ga++) {
    var Ua = Zc[Ga], ny = Ua.toLowerCase(), ry = Ua[0].toUpperCase() + Ua.slice(1);
    yr(ny, "on" + ry);
  }
  yr(Rh, "onAnimationEnd");
  yr(Ah, "onAnimationIteration");
  yr(Lh, "onAnimationStart");
  yr("dblclick", "onDoubleClick");
  yr("focusin", "onFocus");
  yr("focusout", "onBlur");
  yr(Ih, "onTransitionEnd");
  ui("onMouseEnter", [
    "mouseout",
    "mouseover"
  ]);
  ui("onMouseLeave", [
    "mouseout",
    "mouseover"
  ]);
  ui("onPointerEnter", [
    "pointerout",
    "pointerover"
  ]);
  ui("onPointerLeave", [
    "pointerout",
    "pointerover"
  ]);
  Or("onChange", "change click focusin focusout input keydown keyup selectionchange".split(" "));
  Or("onSelect", "focusout contextmenu dragend focusin keydown keyup mousedown mouseup selectionchange".split(" "));
  Or("onBeforeInput", [
    "compositionend",
    "keypress",
    "textInput",
    "paste"
  ]);
  Or("onCompositionEnd", "compositionend focusout keydown keypress keyup mousedown".split(" "));
  Or("onCompositionStart", "compositionstart focusout keydown keypress keyup mousedown".split(" "));
  Or("onCompositionUpdate", "compositionupdate focusout keydown keypress keyup mousedown".split(" "));
  var Xi = "abort canplay canplaythrough durationchange emptied encrypted ended error loadeddata loadedmetadata loadstart pause play playing progress ratechange resize seeked seeking stalled suspend timeupdate volumechange waiting".split(" "), iy = new Set("cancel close invalid load scroll toggle".split(" ").concat(Xi));
  function qc(e, t, n) {
    var r = e.type || "unknown-event";
    e.currentTarget = n, nv(r, t, void 0, e), e.currentTarget = null;
  }
  function Ph(e, t) {
    t = (t & 4) !== 0;
    for (var n = 0; n < e.length; n++) {
      var r = e[n], i = r.event;
      r = r.listeners;
      e: {
        var o = void 0;
        if (t) for (var s = r.length - 1; 0 <= s; s--) {
          var a = r[s], l = a.instance, c = a.currentTarget;
          if (a = a.listener, l !== o && i.isPropagationStopped()) break e;
          qc(i, a, c), o = l;
        }
        else for (s = 0; s < r.length; s++) {
          if (a = r[s], l = a.instance, c = a.currentTarget, a = a.listener, l !== o && i.isPropagationStopped()) break e;
          qc(i, a, c), o = l;
        }
      }
    }
    if (Cs) throw e = Ll, Cs = false, Ll = null, e;
  }
  function Oe(e, t) {
    var n = t[Bl];
    n === void 0 && (n = t[Bl] = /* @__PURE__ */ new Set());
    var r = e + "__bubble";
    n.has(r) || (Nh(t, e, 2, false), n.add(r));
  }
  function Ba(e, t, n) {
    var r = 0;
    t && (r |= 4), Nh(n, e, r, t);
  }
  var Vo = "_reactListening" + Math.random().toString(36).slice(2);
  function vo(e) {
    if (!e[Vo]) {
      e[Vo] = true, Mf.forEach(function(n) {
        n !== "selectionchange" && (iy.has(n) || Ba(n, false, e), Ba(n, true, e));
      });
      var t = e.nodeType === 9 ? e : e.ownerDocument;
      t === null || t[Vo] || (t[Vo] = true, Ba("selectionchange", false, t));
    }
  }
  function Nh(e, t, n, r) {
    switch (vh(t)) {
      case 1:
        var i = yv;
        break;
      case 4:
        i = wv;
        break;
      default:
        i = Iu;
    }
    n = i.bind(null, t, n, e), i = void 0, !Al || t !== "touchstart" && t !== "touchmove" && t !== "wheel" || (i = true), r ? i !== void 0 ? e.addEventListener(t, n, {
      capture: true,
      passive: i
    }) : e.addEventListener(t, n, true) : i !== void 0 ? e.addEventListener(t, n, {
      passive: i
    }) : e.addEventListener(t, n, false);
  }
  function Ma(e, t, n, r, i) {
    var o = r;
    if (!(t & 1) && !(t & 2) && r !== null) e: for (; ; ) {
      if (r === null) return;
      var s = r.tag;
      if (s === 3 || s === 4) {
        var a = r.stateNode.containerInfo;
        if (a === i || a.nodeType === 8 && a.parentNode === i) break;
        if (s === 4) for (s = r.return; s !== null; ) {
          var l = s.tag;
          if ((l === 3 || l === 4) && (l = s.stateNode.containerInfo, l === i || l.nodeType === 8 && l.parentNode === i)) return;
          s = s.return;
        }
        for (; a !== null; ) {
          if (s = Tr(a), s === null) return;
          if (l = s.tag, l === 5 || l === 6) {
            r = o = s;
            continue e;
          }
          a = a.parentNode;
        }
      }
      r = r.return;
    }
    rh(function() {
      var c = o, h = Tu(n), f = [];
      e: {
        var p = Dh.get(e);
        if (p !== void 0) {
          var y = Pu, k = e;
          switch (e) {
            case "keypress":
              if (hs(n) === 0) break e;
            case "keydown":
            case "keyup":
              y = Nv;
              break;
            case "focusin":
              k = "focus", y = Na;
              break;
            case "focusout":
              k = "blur", y = Na;
              break;
            case "beforeblur":
            case "afterblur":
              y = Na;
              break;
            case "click":
              if (n.button === 2) break e;
            case "auxclick":
            case "dblclick":
            case "mousedown":
            case "mousemove":
            case "mouseup":
            case "mouseout":
            case "mouseover":
            case "contextmenu":
              y = Bc;
              break;
            case "drag":
            case "dragend":
            case "dragenter":
            case "dragexit":
            case "dragleave":
            case "dragover":
            case "dragstart":
            case "drop":
              y = _v;
              break;
            case "touchcancel":
            case "touchend":
            case "touchmove":
            case "touchstart":
              y = Ov;
              break;
            case Rh:
            case Ah:
            case Lh:
              y = xv;
              break;
            case Ih:
              y = Uv;
              break;
            case "scroll":
              y = Ev;
              break;
            case "wheel":
              y = Mv;
              break;
            case "copy":
            case "cut":
            case "paste":
              y = Tv;
              break;
            case "gotpointercapture":
            case "lostpointercapture":
            case "pointercancel":
            case "pointerdown":
            case "pointermove":
            case "pointerout":
            case "pointerover":
            case "pointerup":
              y = $c;
          }
          var b = (t & 4) !== 0, I = !b && e === "scroll", _ = b ? p !== null ? p + "Capture" : null : p;
          b = [];
          for (var m = c, v; m !== null; ) {
            v = m;
            var E = v.stateNode;
            if (v.tag === 5 && E !== null && (v = E, _ !== null && (E = co(m, _), E != null && b.push(yo(m, E, v)))), I) break;
            m = m.return;
          }
          0 < b.length && (p = new y(p, k, null, n, h), f.push({
            event: p,
            listeners: b
          }));
        }
      }
      if (!(t & 7)) {
        e: {
          if (p = e === "mouseover" || e === "pointerover", y = e === "mouseout" || e === "pointerout", p && n !== Tl && (k = n.relatedTarget || n.fromElement) && (Tr(k) || k[Wn])) break e;
          if ((y || p) && (p = h.window === h ? h : (p = h.ownerDocument) ? p.defaultView || p.parentWindow : window, y ? (k = n.relatedTarget || n.toElement, y = c, k = k ? Tr(k) : null, k !== null && (I = Gr(k), k !== I || k.tag !== 5 && k.tag !== 6) && (k = null)) : (y = null, k = c), y !== k)) {
            if (b = Bc, E = "onMouseLeave", _ = "onMouseEnter", m = "mouse", (e === "pointerout" || e === "pointerover") && (b = $c, E = "onPointerLeave", _ = "onPointerEnter", m = "pointer"), I = y == null ? p : Yr(y), v = k == null ? p : Yr(k), p = new b(E, m + "leave", y, n, h), p.target = I, p.relatedTarget = v, E = null, Tr(h) === c && (b = new b(_, m + "enter", k, n, h), b.target = v, b.relatedTarget = I, E = b), I = E, y && k) t: {
              for (b = y, _ = k, m = 0, v = b; v; v = Ur(v)) m++;
              for (v = 0, E = _; E; E = Ur(E)) v++;
              for (; 0 < m - v; ) b = Ur(b), m--;
              for (; 0 < v - m; ) _ = Ur(_), v--;
              for (; m--; ) {
                if (b === _ || _ !== null && b === _.alternate) break t;
                b = Ur(b), _ = Ur(_);
              }
              b = null;
            }
            else b = null;
            y !== null && Jc(f, p, y, b, false), k !== null && I !== null && Jc(f, I, k, b, true);
          }
        }
        e: {
          if (p = c ? Yr(c) : window, y = p.nodeName && p.nodeName.toLowerCase(), y === "select" || y === "input" && p.type === "file") var A = Yv;
          else if (Wc(p)) if (kh) A = qv;
          else {
            A = Xv;
            var F = Qv;
          }
          else (y = p.nodeName) && y.toLowerCase() === "input" && (p.type === "checkbox" || p.type === "radio") && (A = Zv);
          if (A && (A = A(e, c))) {
            _h(f, A, n, h);
            break e;
          }
          F && F(e, p, c), e === "focusout" && (F = p._wrapperState) && F.controlled && p.type === "number" && _l(p, "number", p.value);
        }
        switch (F = c ? Yr(c) : window, e) {
          case "focusin":
            (Wc(F) || F.contentEditable === "true") && (Vr = F, Nl = c, no = null);
            break;
          case "focusout":
            no = Nl = Vr = null;
            break;
          case "mousedown":
            Fl = true;
            break;
          case "contextmenu":
          case "mouseup":
          case "dragend":
            Fl = false, Xc(f, n, h);
            break;
          case "selectionchange":
            if (ty) break;
          case "keydown":
          case "keyup":
            Xc(f, n, h);
        }
        var R;
        if (Fu) e: {
          switch (e) {
            case "compositionstart":
              var L = "onCompositionStart";
              break e;
            case "compositionend":
              L = "onCompositionEnd";
              break e;
            case "compositionupdate":
              L = "onCompositionUpdate";
              break e;
          }
          L = void 0;
        }
        else Wr ? Eh(e, n) && (L = "onCompositionEnd") : e === "keydown" && n.keyCode === 229 && (L = "onCompositionStart");
        L && (wh && n.locale !== "ko" && (Wr || L !== "onCompositionStart" ? L === "onCompositionEnd" && Wr && (R = yh()) : (sr = h, Du = "value" in sr ? sr.value : sr.textContent, Wr = true)), F = Is(c, L), 0 < F.length && (L = new Mc(L, e, null, n, h), f.push({
          event: L,
          listeners: F
        }), R ? L.data = R : (R = Sh(n), R !== null && (L.data = R)))), (R = jv ? Hv(e, n) : Wv(e, n)) && (c = Is(c, "onBeforeInput"), 0 < c.length && (h = new Mc("onBeforeInput", "beforeinput", null, n, h), f.push({
          event: h,
          listeners: c
        }), h.data = R));
      }
      Ph(f, t);
    });
  }
  function yo(e, t, n) {
    return {
      instance: e,
      listener: t,
      currentTarget: n
    };
  }
  function Is(e, t) {
    for (var n = t + "Capture", r = []; e !== null; ) {
      var i = e, o = i.stateNode;
      i.tag === 5 && o !== null && (i = o, o = co(e, n), o != null && r.unshift(yo(e, o, i)), o = co(e, t), o != null && r.push(yo(e, o, i))), e = e.return;
    }
    return r;
  }
  function Ur(e) {
    if (e === null) return null;
    do
      e = e.return;
    while (e && e.tag !== 5);
    return e || null;
  }
  function Jc(e, t, n, r, i) {
    for (var o = t._reactName, s = []; n !== null && n !== r; ) {
      var a = n, l = a.alternate, c = a.stateNode;
      if (l !== null && l === r) break;
      a.tag === 5 && c !== null && (a = c, i ? (l = co(n, o), l != null && s.unshift(yo(n, l, a))) : i || (l = co(n, o), l != null && s.push(yo(n, l, a)))), n = n.return;
    }
    s.length !== 0 && e.push({
      event: t,
      listeners: s
    });
  }
  var oy = /\r\n?/g, sy = /\u0000|\uFFFD/g;
  function ed(e) {
    return (typeof e == "string" ? e : "" + e).replace(oy, `
`).replace(sy, "");
  }
  function Ko(e, t, n) {
    if (t = ed(t), ed(e) !== t && n) throw Error(W(425));
  }
  function Ds() {
  }
  var zl = null, Ol = null;
  function Gl(e, t) {
    return e === "textarea" || e === "noscript" || typeof t.children == "string" || typeof t.children == "number" || typeof t.dangerouslySetInnerHTML == "object" && t.dangerouslySetInnerHTML !== null && t.dangerouslySetInnerHTML.__html != null;
  }
  var Ul = typeof setTimeout == "function" ? setTimeout : void 0, ay = typeof clearTimeout == "function" ? clearTimeout : void 0, td = typeof Promise == "function" ? Promise : void 0, ly = typeof queueMicrotask == "function" ? queueMicrotask : typeof td < "u" ? function(e) {
    return td.resolve(null).then(e).catch(uy);
  } : Ul;
  function uy(e) {
    setTimeout(function() {
      throw e;
    });
  }
  function $a(e, t) {
    var n = t, r = 0;
    do {
      var i = n.nextSibling;
      if (e.removeChild(n), i && i.nodeType === 8) if (n = i.data, n === "/$") {
        if (r === 0) {
          e.removeChild(i), po(t);
          return;
        }
        r--;
      } else n !== "$" && n !== "$?" && n !== "$!" || r++;
      n = i;
    } while (n);
    po(t);
  }
  function dr(e) {
    for (; e != null; e = e.nextSibling) {
      var t = e.nodeType;
      if (t === 1 || t === 3) break;
      if (t === 8) {
        if (t = e.data, t === "$" || t === "$!" || t === "$?") break;
        if (t === "/$") return null;
      }
    }
    return e;
  }
  function nd(e) {
    e = e.previousSibling;
    for (var t = 0; e; ) {
      if (e.nodeType === 8) {
        var n = e.data;
        if (n === "$" || n === "$!" || n === "$?") {
          if (t === 0) return e;
          t--;
        } else n === "/$" && t++;
      }
      e = e.previousSibling;
    }
    return null;
  }
  var Si = Math.random().toString(36).slice(2), Tn = "__reactFiber$" + Si, wo = "__reactProps$" + Si, Wn = "__reactContainer$" + Si, Bl = "__reactEvents$" + Si, cy = "__reactListeners$" + Si, dy = "__reactHandles$" + Si;
  function Tr(e) {
    var t = e[Tn];
    if (t) return t;
    for (var n = e.parentNode; n; ) {
      if (t = n[Wn] || n[Tn]) {
        if (n = t.alternate, t.child !== null || n !== null && n.child !== null) for (e = nd(e); e !== null; ) {
          if (n = e[Tn]) return n;
          e = nd(e);
        }
        return t;
      }
      e = n, n = e.parentNode;
    }
    return null;
  }
  function Io(e) {
    return e = e[Tn] || e[Wn], !e || e.tag !== 5 && e.tag !== 6 && e.tag !== 13 && e.tag !== 3 ? null : e;
  }
  function Yr(e) {
    if (e.tag === 5 || e.tag === 6) return e.stateNode;
    throw Error(W(33));
  }
  function sa(e) {
    return e[wo] || null;
  }
  var Ml = [], Qr = -1;
  function wr(e) {
    return {
      current: e
    };
  }
  function Ge(e) {
    0 > Qr || (e.current = Ml[Qr], Ml[Qr] = null, Qr--);
  }
  function Fe(e, t) {
    Qr++, Ml[Qr] = e.current, e.current = t;
  }
  var vr = {}, xt = wr(vr), Ut = wr(false), Dr = vr;
  function ci(e, t) {
    var n = e.type.contextTypes;
    if (!n) return vr;
    var r = e.stateNode;
    if (r && r.__reactInternalMemoizedUnmaskedChildContext === t) return r.__reactInternalMemoizedMaskedChildContext;
    var i = {}, o;
    for (o in n) i[o] = t[o];
    return r && (e = e.stateNode, e.__reactInternalMemoizedUnmaskedChildContext = t, e.__reactInternalMemoizedMaskedChildContext = i), i;
  }
  function Bt(e) {
    return e = e.childContextTypes, e != null;
  }
  function Ps() {
    Ge(Ut), Ge(xt);
  }
  function rd(e, t, n) {
    if (xt.current !== vr) throw Error(W(168));
    Fe(xt, t), Fe(Ut, n);
  }
  function Fh(e, t, n) {
    var r = e.stateNode;
    if (t = t.childContextTypes, typeof r.getChildContext != "function") return n;
    r = r.getChildContext();
    for (var i in r) if (!(i in t)) throw Error(W(108, Qm(e) || "Unknown", i));
    return je({}, n, r);
  }
  function Ns(e) {
    return e = (e = e.stateNode) && e.__reactInternalMemoizedMergedChildContext || vr, Dr = xt.current, Fe(xt, e), Fe(Ut, Ut.current), true;
  }
  function id(e, t, n) {
    var r = e.stateNode;
    if (!r) throw Error(W(169));
    n ? (e = Fh(e, t, Dr), r.__reactInternalMemoizedMergedChildContext = e, Ge(Ut), Ge(xt), Fe(xt, e)) : Ge(Ut), Fe(Ut, n);
  }
  var Gn = null, aa = false, ja = false;
  function zh(e) {
    Gn === null ? Gn = [
      e
    ] : Gn.push(e);
  }
  function fy(e) {
    aa = true, zh(e);
  }
  function Er() {
    if (!ja && Gn !== null) {
      ja = true;
      var e = 0, t = De;
      try {
        var n = Gn;
        for (De = 1; e < n.length; e++) {
          var r = n[e];
          do
            r = r(true);
          while (r !== null);
        }
        Gn = null, aa = false;
      } catch (i) {
        throw Gn !== null && (Gn = Gn.slice(e + 1)), ah(Ru, Er), i;
      } finally {
        De = t, ja = false;
      }
    }
    return null;
  }
  var Xr = [], Zr = 0, Fs = null, zs = 0, qt = [], Jt = 0, Pr = null, Bn = 1, Mn = "";
  function br(e, t) {
    Xr[Zr++] = zs, Xr[Zr++] = Fs, Fs = e, zs = t;
  }
  function Oh(e, t, n) {
    qt[Jt++] = Bn, qt[Jt++] = Mn, qt[Jt++] = Pr, Pr = e;
    var r = Bn;
    e = Mn;
    var i = 32 - wn(r) - 1;
    r &= ~(1 << i), n += 1;
    var o = 32 - wn(t) + i;
    if (30 < o) {
      var s = i - i % 5;
      o = (r & (1 << s) - 1).toString(32), r >>= s, i -= s, Bn = 1 << 32 - wn(t) + i | n << i | r, Mn = o + e;
    } else Bn = 1 << o | n << i | r, Mn = e;
  }
  function Ou(e) {
    e.return !== null && (br(e, 1), Oh(e, 1, 0));
  }
  function Gu(e) {
    for (; e === Fs; ) Fs = Xr[--Zr], Xr[Zr] = null, zs = Xr[--Zr], Xr[Zr] = null;
    for (; e === Pr; ) Pr = qt[--Jt], qt[Jt] = null, Mn = qt[--Jt], qt[Jt] = null, Bn = qt[--Jt], qt[Jt] = null;
  }
  var Wt = null, Ht = null, Ue = false, vn = null;
  function Gh(e, t) {
    var n = en(5, null, null, 0);
    n.elementType = "DELETED", n.stateNode = t, n.return = e, t = e.deletions, t === null ? (e.deletions = [
      n
    ], e.flags |= 16) : t.push(n);
  }
  function od(e, t) {
    switch (e.tag) {
      case 5:
        var n = e.type;
        return t = t.nodeType !== 1 || n.toLowerCase() !== t.nodeName.toLowerCase() ? null : t, t !== null ? (e.stateNode = t, Wt = e, Ht = dr(t.firstChild), true) : false;
      case 6:
        return t = e.pendingProps === "" || t.nodeType !== 3 ? null : t, t !== null ? (e.stateNode = t, Wt = e, Ht = null, true) : false;
      case 13:
        return t = t.nodeType !== 8 ? null : t, t !== null ? (n = Pr !== null ? {
          id: Bn,
          overflow: Mn
        } : null, e.memoizedState = {
          dehydrated: t,
          treeContext: n,
          retryLane: 1073741824
        }, n = en(18, null, null, 0), n.stateNode = t, n.return = e, e.child = n, Wt = e, Ht = null, true) : false;
      default:
        return false;
    }
  }
  function $l(e) {
    return (e.mode & 1) !== 0 && (e.flags & 128) === 0;
  }
  function jl(e) {
    if (Ue) {
      var t = Ht;
      if (t) {
        var n = t;
        if (!od(e, t)) {
          if ($l(e)) throw Error(W(418));
          t = dr(n.nextSibling);
          var r = Wt;
          t && od(e, t) ? Gh(r, n) : (e.flags = e.flags & -4097 | 2, Ue = false, Wt = e);
        }
      } else {
        if ($l(e)) throw Error(W(418));
        e.flags = e.flags & -4097 | 2, Ue = false, Wt = e;
      }
    }
  }
  function sd(e) {
    for (e = e.return; e !== null && e.tag !== 5 && e.tag !== 3 && e.tag !== 13; ) e = e.return;
    Wt = e;
  }
  function Yo(e) {
    if (e !== Wt) return false;
    if (!Ue) return sd(e), Ue = true, false;
    var t;
    if ((t = e.tag !== 3) && !(t = e.tag !== 5) && (t = e.type, t = t !== "head" && t !== "body" && !Gl(e.type, e.memoizedProps)), t && (t = Ht)) {
      if ($l(e)) throw Uh(), Error(W(418));
      for (; t; ) Gh(e, t), t = dr(t.nextSibling);
    }
    if (sd(e), e.tag === 13) {
      if (e = e.memoizedState, e = e !== null ? e.dehydrated : null, !e) throw Error(W(317));
      e: {
        for (e = e.nextSibling, t = 0; e; ) {
          if (e.nodeType === 8) {
            var n = e.data;
            if (n === "/$") {
              if (t === 0) {
                Ht = dr(e.nextSibling);
                break e;
              }
              t--;
            } else n !== "$" && n !== "$!" && n !== "$?" || t++;
          }
          e = e.nextSibling;
        }
        Ht = null;
      }
    } else Ht = Wt ? dr(e.stateNode.nextSibling) : null;
    return true;
  }
  function Uh() {
    for (var e = Ht; e; ) e = dr(e.nextSibling);
  }
  function di() {
    Ht = Wt = null, Ue = false;
  }
  function Uu(e) {
    vn === null ? vn = [
      e
    ] : vn.push(e);
  }
  var hy = Yn.ReactCurrentBatchConfig;
  function Ni(e, t, n) {
    if (e = n.ref, e !== null && typeof e != "function" && typeof e != "object") {
      if (n._owner) {
        if (n = n._owner, n) {
          if (n.tag !== 1) throw Error(W(309));
          var r = n.stateNode;
        }
        if (!r) throw Error(W(147, e));
        var i = r, o = "" + e;
        return t !== null && t.ref !== null && typeof t.ref == "function" && t.ref._stringRef === o ? t.ref : (t = function(s) {
          var a = i.refs;
          s === null ? delete a[o] : a[o] = s;
        }, t._stringRef = o, t);
      }
      if (typeof e != "string") throw Error(W(284));
      if (!n._owner) throw Error(W(290, e));
    }
    return e;
  }
  function Qo(e, t) {
    throw e = Object.prototype.toString.call(t), Error(W(31, e === "[object Object]" ? "object with keys {" + Object.keys(t).join(", ") + "}" : e));
  }
  function ad(e) {
    var t = e._init;
    return t(e._payload);
  }
  function Bh(e) {
    function t(_, m) {
      if (e) {
        var v = _.deletions;
        v === null ? (_.deletions = [
          m
        ], _.flags |= 16) : v.push(m);
      }
    }
    function n(_, m) {
      if (!e) return null;
      for (; m !== null; ) t(_, m), m = m.sibling;
      return null;
    }
    function r(_, m) {
      for (_ = /* @__PURE__ */ new Map(); m !== null; ) m.key !== null ? _.set(m.key, m) : _.set(m.index, m), m = m.sibling;
      return _;
    }
    function i(_, m) {
      return _ = gr(_, m), _.index = 0, _.sibling = null, _;
    }
    function o(_, m, v) {
      return _.index = v, e ? (v = _.alternate, v !== null ? (v = v.index, v < m ? (_.flags |= 2, m) : v) : (_.flags |= 2, m)) : (_.flags |= 1048576, m);
    }
    function s(_) {
      return e && _.alternate === null && (_.flags |= 2), _;
    }
    function a(_, m, v, E) {
      return m === null || m.tag !== 6 ? (m = Xa(v, _.mode, E), m.return = _, m) : (m = i(m, v), m.return = _, m);
    }
    function l(_, m, v, E) {
      var A = v.type;
      return A === Hr ? h(_, m, v.props.children, E, v.key) : m !== null && (m.elementType === A || typeof A == "object" && A !== null && A.$$typeof === nr && ad(A) === m.type) ? (E = i(m, v.props), E.ref = Ni(_, m, v), E.return = _, E) : (E = Es(v.type, v.key, v.props, null, _.mode, E), E.ref = Ni(_, m, v), E.return = _, E);
    }
    function c(_, m, v, E) {
      return m === null || m.tag !== 4 || m.stateNode.containerInfo !== v.containerInfo || m.stateNode.implementation !== v.implementation ? (m = Za(v, _.mode, E), m.return = _, m) : (m = i(m, v.children || []), m.return = _, m);
    }
    function h(_, m, v, E, A) {
      return m === null || m.tag !== 7 ? (m = Ir(v, _.mode, E, A), m.return = _, m) : (m = i(m, v), m.return = _, m);
    }
    function f(_, m, v) {
      if (typeof m == "string" && m !== "" || typeof m == "number") return m = Xa("" + m, _.mode, v), m.return = _, m;
      if (typeof m == "object" && m !== null) {
        switch (m.$$typeof) {
          case Go:
            return v = Es(m.type, m.key, m.props, null, _.mode, v), v.ref = Ni(_, null, m), v.return = _, v;
          case jr:
            return m = Za(m, _.mode, v), m.return = _, m;
          case nr:
            var E = m._init;
            return f(_, E(m._payload), v);
        }
        if (Yi(m) || Ai(m)) return m = Ir(m, _.mode, v, null), m.return = _, m;
        Qo(_, m);
      }
      return null;
    }
    function p(_, m, v, E) {
      var A = m !== null ? m.key : null;
      if (typeof v == "string" && v !== "" || typeof v == "number") return A !== null ? null : a(_, m, "" + v, E);
      if (typeof v == "object" && v !== null) {
        switch (v.$$typeof) {
          case Go:
            return v.key === A ? l(_, m, v, E) : null;
          case jr:
            return v.key === A ? c(_, m, v, E) : null;
          case nr:
            return A = v._init, p(_, m, A(v._payload), E);
        }
        if (Yi(v) || Ai(v)) return A !== null ? null : h(_, m, v, E, null);
        Qo(_, v);
      }
      return null;
    }
    function y(_, m, v, E, A) {
      if (typeof E == "string" && E !== "" || typeof E == "number") return _ = _.get(v) || null, a(m, _, "" + E, A);
      if (typeof E == "object" && E !== null) {
        switch (E.$$typeof) {
          case Go:
            return _ = _.get(E.key === null ? v : E.key) || null, l(m, _, E, A);
          case jr:
            return _ = _.get(E.key === null ? v : E.key) || null, c(m, _, E, A);
          case nr:
            var F = E._init;
            return y(_, m, v, F(E._payload), A);
        }
        if (Yi(E) || Ai(E)) return _ = _.get(v) || null, h(m, _, E, A, null);
        Qo(m, E);
      }
      return null;
    }
    function k(_, m, v, E) {
      for (var A = null, F = null, R = m, L = m = 0, C = null; R !== null && L < v.length; L++) {
        R.index > L ? (C = R, R = null) : C = R.sibling;
        var N = p(_, R, v[L], E);
        if (N === null) {
          R === null && (R = C);
          break;
        }
        e && R && N.alternate === null && t(_, R), m = o(N, m, L), F === null ? A = N : F.sibling = N, F = N, R = C;
      }
      if (L === v.length) return n(_, R), Ue && br(_, L), A;
      if (R === null) {
        for (; L < v.length; L++) R = f(_, v[L], E), R !== null && (m = o(R, m, L), F === null ? A = R : F.sibling = R, F = R);
        return Ue && br(_, L), A;
      }
      for (R = r(_, R); L < v.length; L++) C = y(R, _, L, v[L], E), C !== null && (e && C.alternate !== null && R.delete(C.key === null ? L : C.key), m = o(C, m, L), F === null ? A = C : F.sibling = C, F = C);
      return e && R.forEach(function(V) {
        return t(_, V);
      }), Ue && br(_, L), A;
    }
    function b(_, m, v, E) {
      var A = Ai(v);
      if (typeof A != "function") throw Error(W(150));
      if (v = A.call(v), v == null) throw Error(W(151));
      for (var F = A = null, R = m, L = m = 0, C = null, N = v.next(); R !== null && !N.done; L++, N = v.next()) {
        R.index > L ? (C = R, R = null) : C = R.sibling;
        var V = p(_, R, N.value, E);
        if (V === null) {
          R === null && (R = C);
          break;
        }
        e && R && V.alternate === null && t(_, R), m = o(V, m, L), F === null ? A = V : F.sibling = V, F = V, R = C;
      }
      if (N.done) return n(_, R), Ue && br(_, L), A;
      if (R === null) {
        for (; !N.done; L++, N = v.next()) N = f(_, N.value, E), N !== null && (m = o(N, m, L), F === null ? A = N : F.sibling = N, F = N);
        return Ue && br(_, L), A;
      }
      for (R = r(_, R); !N.done; L++, N = v.next()) N = y(R, _, L, N.value, E), N !== null && (e && N.alternate !== null && R.delete(N.key === null ? L : N.key), m = o(N, m, L), F === null ? A = N : F.sibling = N, F = N);
      return e && R.forEach(function(B) {
        return t(_, B);
      }), Ue && br(_, L), A;
    }
    function I(_, m, v, E) {
      if (typeof v == "object" && v !== null && v.type === Hr && v.key === null && (v = v.props.children), typeof v == "object" && v !== null) {
        switch (v.$$typeof) {
          case Go:
            e: {
              for (var A = v.key, F = m; F !== null; ) {
                if (F.key === A) {
                  if (A = v.type, A === Hr) {
                    if (F.tag === 7) {
                      n(_, F.sibling), m = i(F, v.props.children), m.return = _, _ = m;
                      break e;
                    }
                  } else if (F.elementType === A || typeof A == "object" && A !== null && A.$$typeof === nr && ad(A) === F.type) {
                    n(_, F.sibling), m = i(F, v.props), m.ref = Ni(_, F, v), m.return = _, _ = m;
                    break e;
                  }
                  n(_, F);
                  break;
                } else t(_, F);
                F = F.sibling;
              }
              v.type === Hr ? (m = Ir(v.props.children, _.mode, E, v.key), m.return = _, _ = m) : (E = Es(v.type, v.key, v.props, null, _.mode, E), E.ref = Ni(_, m, v), E.return = _, _ = E);
            }
            return s(_);
          case jr:
            e: {
              for (F = v.key; m !== null; ) {
                if (m.key === F) if (m.tag === 4 && m.stateNode.containerInfo === v.containerInfo && m.stateNode.implementation === v.implementation) {
                  n(_, m.sibling), m = i(m, v.children || []), m.return = _, _ = m;
                  break e;
                } else {
                  n(_, m);
                  break;
                }
                else t(_, m);
                m = m.sibling;
              }
              m = Za(v, _.mode, E), m.return = _, _ = m;
            }
            return s(_);
          case nr:
            return F = v._init, I(_, m, F(v._payload), E);
        }
        if (Yi(v)) return k(_, m, v, E);
        if (Ai(v)) return b(_, m, v, E);
        Qo(_, v);
      }
      return typeof v == "string" && v !== "" || typeof v == "number" ? (v = "" + v, m !== null && m.tag === 6 ? (n(_, m.sibling), m = i(m, v), m.return = _, _ = m) : (n(_, m), m = Xa(v, _.mode, E), m.return = _, _ = m), s(_)) : n(_, m);
    }
    return I;
  }
  var fi = Bh(true), Mh = Bh(false), Os = wr(null), Gs = null, qr = null, Bu = null;
  function Mu() {
    Bu = qr = Gs = null;
  }
  function $u(e) {
    var t = Os.current;
    Ge(Os), e._currentValue = t;
  }
  function Hl(e, t, n) {
    for (; e !== null; ) {
      var r = e.alternate;
      if ((e.childLanes & t) !== t ? (e.childLanes |= t, r !== null && (r.childLanes |= t)) : r !== null && (r.childLanes & t) !== t && (r.childLanes |= t), e === n) break;
      e = e.return;
    }
  }
  function oi(e, t) {
    Gs = e, Bu = qr = null, e = e.dependencies, e !== null && e.firstContext !== null && (e.lanes & t && (Gt = true), e.firstContext = null);
  }
  function rn(e) {
    var t = e._currentValue;
    if (Bu !== e) if (e = {
      context: e,
      memoizedValue: t,
      next: null
    }, qr === null) {
      if (Gs === null) throw Error(W(308));
      qr = e, Gs.dependencies = {
        lanes: 0,
        firstContext: e
      };
    } else qr = qr.next = e;
    return t;
  }
  var Rr = null;
  function ju(e) {
    Rr === null ? Rr = [
      e
    ] : Rr.push(e);
  }
  function $h(e, t, n, r) {
    var i = t.interleaved;
    return i === null ? (n.next = n, ju(t)) : (n.next = i.next, i.next = n), t.interleaved = n, Vn(e, r);
  }
  function Vn(e, t) {
    e.lanes |= t;
    var n = e.alternate;
    for (n !== null && (n.lanes |= t), n = e, e = e.return; e !== null; ) e.childLanes |= t, n = e.alternate, n !== null && (n.childLanes |= t), n = e, e = e.return;
    return n.tag === 3 ? n.stateNode : null;
  }
  var rr = false;
  function Hu(e) {
    e.updateQueue = {
      baseState: e.memoizedState,
      firstBaseUpdate: null,
      lastBaseUpdate: null,
      shared: {
        pending: null,
        interleaved: null,
        lanes: 0
      },
      effects: null
    };
  }
  function jh(e, t) {
    e = e.updateQueue, t.updateQueue === e && (t.updateQueue = {
      baseState: e.baseState,
      firstBaseUpdate: e.firstBaseUpdate,
      lastBaseUpdate: e.lastBaseUpdate,
      shared: e.shared,
      effects: e.effects
    });
  }
  function $n(e, t) {
    return {
      eventTime: e,
      lane: t,
      tag: 0,
      payload: null,
      callback: null,
      next: null
    };
  }
  function fr(e, t, n) {
    var r = e.updateQueue;
    if (r === null) return null;
    if (r = r.shared, be & 2) {
      var i = r.pending;
      return i === null ? t.next = t : (t.next = i.next, i.next = t), r.pending = t, Vn(e, n);
    }
    return i = r.interleaved, i === null ? (t.next = t, ju(r)) : (t.next = i.next, i.next = t), r.interleaved = t, Vn(e, n);
  }
  function ps(e, t, n) {
    if (t = t.updateQueue, t !== null && (t = t.shared, (n & 4194240) !== 0)) {
      var r = t.lanes;
      r &= e.pendingLanes, n |= r, t.lanes = n, Au(e, n);
    }
  }
  function ld(e, t) {
    var n = e.updateQueue, r = e.alternate;
    if (r !== null && (r = r.updateQueue, n === r)) {
      var i = null, o = null;
      if (n = n.firstBaseUpdate, n !== null) {
        do {
          var s = {
            eventTime: n.eventTime,
            lane: n.lane,
            tag: n.tag,
            payload: n.payload,
            callback: n.callback,
            next: null
          };
          o === null ? i = o = s : o = o.next = s, n = n.next;
        } while (n !== null);
        o === null ? i = o = t : o = o.next = t;
      } else i = o = t;
      n = {
        baseState: r.baseState,
        firstBaseUpdate: i,
        lastBaseUpdate: o,
        shared: r.shared,
        effects: r.effects
      }, e.updateQueue = n;
      return;
    }
    e = n.lastBaseUpdate, e === null ? n.firstBaseUpdate = t : e.next = t, n.lastBaseUpdate = t;
  }
  function Us(e, t, n, r) {
    var i = e.updateQueue;
    rr = false;
    var o = i.firstBaseUpdate, s = i.lastBaseUpdate, a = i.shared.pending;
    if (a !== null) {
      i.shared.pending = null;
      var l = a, c = l.next;
      l.next = null, s === null ? o = c : s.next = c, s = l;
      var h = e.alternate;
      h !== null && (h = h.updateQueue, a = h.lastBaseUpdate, a !== s && (a === null ? h.firstBaseUpdate = c : a.next = c, h.lastBaseUpdate = l));
    }
    if (o !== null) {
      var f = i.baseState;
      s = 0, h = c = l = null, a = o;
      do {
        var p = a.lane, y = a.eventTime;
        if ((r & p) === p) {
          h !== null && (h = h.next = {
            eventTime: y,
            lane: 0,
            tag: a.tag,
            payload: a.payload,
            callback: a.callback,
            next: null
          });
          e: {
            var k = e, b = a;
            switch (p = t, y = n, b.tag) {
              case 1:
                if (k = b.payload, typeof k == "function") {
                  f = k.call(y, f, p);
                  break e;
                }
                f = k;
                break e;
              case 3:
                k.flags = k.flags & -65537 | 128;
              case 0:
                if (k = b.payload, p = typeof k == "function" ? k.call(y, f, p) : k, p == null) break e;
                f = je({}, f, p);
                break e;
              case 2:
                rr = true;
            }
          }
          a.callback !== null && a.lane !== 0 && (e.flags |= 64, p = i.effects, p === null ? i.effects = [
            a
          ] : p.push(a));
        } else y = {
          eventTime: y,
          lane: p,
          tag: a.tag,
          payload: a.payload,
          callback: a.callback,
          next: null
        }, h === null ? (c = h = y, l = f) : h = h.next = y, s |= p;
        if (a = a.next, a === null) {
          if (a = i.shared.pending, a === null) break;
          p = a, a = p.next, p.next = null, i.lastBaseUpdate = p, i.shared.pending = null;
        }
      } while (true);
      if (h === null && (l = f), i.baseState = l, i.firstBaseUpdate = c, i.lastBaseUpdate = h, t = i.shared.interleaved, t !== null) {
        i = t;
        do
          s |= i.lane, i = i.next;
        while (i !== t);
      } else o === null && (i.shared.lanes = 0);
      Fr |= s, e.lanes = s, e.memoizedState = f;
    }
  }
  function ud(e, t, n) {
    if (e = t.effects, t.effects = null, e !== null) for (t = 0; t < e.length; t++) {
      var r = e[t], i = r.callback;
      if (i !== null) {
        if (r.callback = null, r = n, typeof i != "function") throw Error(W(191, i));
        i.call(r);
      }
    }
  }
  var Do = {}, Ln = wr(Do), Eo = wr(Do), So = wr(Do);
  function Ar(e) {
    if (e === Do) throw Error(W(174));
    return e;
  }
  function Wu(e, t) {
    switch (Fe(So, t), Fe(Eo, e), Fe(Ln, Do), e = t.nodeType, e) {
      case 9:
      case 11:
        t = (t = t.documentElement) ? t.namespaceURI : bl(null, "");
        break;
      default:
        e = e === 8 ? t.parentNode : t, t = e.namespaceURI || null, e = e.tagName, t = bl(t, e);
    }
    Ge(Ln), Fe(Ln, t);
  }
  function hi() {
    Ge(Ln), Ge(Eo), Ge(So);
  }
  function Hh(e) {
    Ar(So.current);
    var t = Ar(Ln.current), n = bl(t, e.type);
    t !== n && (Fe(Eo, e), Fe(Ln, n));
  }
  function Vu(e) {
    Eo.current === e && (Ge(Ln), Ge(Eo));
  }
  var Me = wr(0);
  function Bs(e) {
    for (var t = e; t !== null; ) {
      if (t.tag === 13) {
        var n = t.memoizedState;
        if (n !== null && (n = n.dehydrated, n === null || n.data === "$?" || n.data === "$!")) return t;
      } else if (t.tag === 19 && t.memoizedProps.revealOrder !== void 0) {
        if (t.flags & 128) return t;
      } else if (t.child !== null) {
        t.child.return = t, t = t.child;
        continue;
      }
      if (t === e) break;
      for (; t.sibling === null; ) {
        if (t.return === null || t.return === e) return null;
        t = t.return;
      }
      t.sibling.return = t.return, t = t.sibling;
    }
    return null;
  }
  var Ha = [];
  function Ku() {
    for (var e = 0; e < Ha.length; e++) Ha[e]._workInProgressVersionPrimary = null;
    Ha.length = 0;
  }
  var gs = Yn.ReactCurrentDispatcher, Wa = Yn.ReactCurrentBatchConfig, Nr = 0, $e = null, rt = null, ct = null, Ms = false, ro = false, _o = 0, py = 0;
  function St() {
    throw Error(W(321));
  }
  function Yu(e, t) {
    if (t === null) return false;
    for (var n = 0; n < t.length && n < e.length; n++) if (!Sn(e[n], t[n])) return false;
    return true;
  }
  function Qu(e, t, n, r, i, o) {
    if (Nr = o, $e = t, t.memoizedState = null, t.updateQueue = null, t.lanes = 0, gs.current = e === null || e.memoizedState === null ? yy : wy, e = n(r, i), ro) {
      o = 0;
      do {
        if (ro = false, _o = 0, 25 <= o) throw Error(W(301));
        o += 1, ct = rt = null, t.updateQueue = null, gs.current = Ey, e = n(r, i);
      } while (ro);
    }
    if (gs.current = $s, t = rt !== null && rt.next !== null, Nr = 0, ct = rt = $e = null, Ms = false, t) throw Error(W(300));
    return e;
  }
  function Xu() {
    var e = _o !== 0;
    return _o = 0, e;
  }
  function Cn() {
    var e = {
      memoizedState: null,
      baseState: null,
      baseQueue: null,
      queue: null,
      next: null
    };
    return ct === null ? $e.memoizedState = ct = e : ct = ct.next = e, ct;
  }
  function on() {
    if (rt === null) {
      var e = $e.alternate;
      e = e !== null ? e.memoizedState : null;
    } else e = rt.next;
    var t = ct === null ? $e.memoizedState : ct.next;
    if (t !== null) ct = t, rt = e;
    else {
      if (e === null) throw Error(W(310));
      rt = e, e = {
        memoizedState: rt.memoizedState,
        baseState: rt.baseState,
        baseQueue: rt.baseQueue,
        queue: rt.queue,
        next: null
      }, ct === null ? $e.memoizedState = ct = e : ct = ct.next = e;
    }
    return ct;
  }
  function ko(e, t) {
    return typeof t == "function" ? t(e) : t;
  }
  function Va(e) {
    var t = on(), n = t.queue;
    if (n === null) throw Error(W(311));
    n.lastRenderedReducer = e;
    var r = rt, i = r.baseQueue, o = n.pending;
    if (o !== null) {
      if (i !== null) {
        var s = i.next;
        i.next = o.next, o.next = s;
      }
      r.baseQueue = i = o, n.pending = null;
    }
    if (i !== null) {
      o = i.next, r = r.baseState;
      var a = s = null, l = null, c = o;
      do {
        var h = c.lane;
        if ((Nr & h) === h) l !== null && (l = l.next = {
          lane: 0,
          action: c.action,
          hasEagerState: c.hasEagerState,
          eagerState: c.eagerState,
          next: null
        }), r = c.hasEagerState ? c.eagerState : e(r, c.action);
        else {
          var f = {
            lane: h,
            action: c.action,
            hasEagerState: c.hasEagerState,
            eagerState: c.eagerState,
            next: null
          };
          l === null ? (a = l = f, s = r) : l = l.next = f, $e.lanes |= h, Fr |= h;
        }
        c = c.next;
      } while (c !== null && c !== o);
      l === null ? s = r : l.next = a, Sn(r, t.memoizedState) || (Gt = true), t.memoizedState = r, t.baseState = s, t.baseQueue = l, n.lastRenderedState = r;
    }
    if (e = n.interleaved, e !== null) {
      i = e;
      do
        o = i.lane, $e.lanes |= o, Fr |= o, i = i.next;
      while (i !== e);
    } else i === null && (n.lanes = 0);
    return [
      t.memoizedState,
      n.dispatch
    ];
  }
  function Ka(e) {
    var t = on(), n = t.queue;
    if (n === null) throw Error(W(311));
    n.lastRenderedReducer = e;
    var r = n.dispatch, i = n.pending, o = t.memoizedState;
    if (i !== null) {
      n.pending = null;
      var s = i = i.next;
      do
        o = e(o, s.action), s = s.next;
      while (s !== i);
      Sn(o, t.memoizedState) || (Gt = true), t.memoizedState = o, t.baseQueue === null && (t.baseState = o), n.lastRenderedState = o;
    }
    return [
      o,
      r
    ];
  }
  function Wh() {
  }
  function Vh(e, t) {
    var n = $e, r = on(), i = t(), o = !Sn(r.memoizedState, i);
    if (o && (r.memoizedState = i, Gt = true), r = r.queue, Zu(Qh.bind(null, n, r, e), [
      e
    ]), r.getSnapshot !== t || o || ct !== null && ct.memoizedState.tag & 1) {
      if (n.flags |= 2048, bo(9, Yh.bind(null, n, r, i, t), void 0, null), dt === null) throw Error(W(349));
      Nr & 30 || Kh(n, t, i);
    }
    return i;
  }
  function Kh(e, t, n) {
    e.flags |= 16384, e = {
      getSnapshot: t,
      value: n
    }, t = $e.updateQueue, t === null ? (t = {
      lastEffect: null,
      stores: null
    }, $e.updateQueue = t, t.stores = [
      e
    ]) : (n = t.stores, n === null ? t.stores = [
      e
    ] : n.push(e));
  }
  function Yh(e, t, n, r) {
    t.value = n, t.getSnapshot = r, Xh(t) && Zh(e);
  }
  function Qh(e, t, n) {
    return n(function() {
      Xh(t) && Zh(e);
    });
  }
  function Xh(e) {
    var t = e.getSnapshot;
    e = e.value;
    try {
      var n = t();
      return !Sn(e, n);
    } catch {
      return true;
    }
  }
  function Zh(e) {
    var t = Vn(e, 1);
    t !== null && En(t, e, 1, -1);
  }
  function cd(e) {
    var t = Cn();
    return typeof e == "function" && (e = e()), t.memoizedState = t.baseState = e, e = {
      pending: null,
      interleaved: null,
      lanes: 0,
      dispatch: null,
      lastRenderedReducer: ko,
      lastRenderedState: e
    }, t.queue = e, e = e.dispatch = vy.bind(null, $e, e), [
      t.memoizedState,
      e
    ];
  }
  function bo(e, t, n, r) {
    return e = {
      tag: e,
      create: t,
      destroy: n,
      deps: r,
      next: null
    }, t = $e.updateQueue, t === null ? (t = {
      lastEffect: null,
      stores: null
    }, $e.updateQueue = t, t.lastEffect = e.next = e) : (n = t.lastEffect, n === null ? t.lastEffect = e.next = e : (r = n.next, n.next = e, e.next = r, t.lastEffect = e)), e;
  }
  function qh() {
    return on().memoizedState;
  }
  function ms(e, t, n, r) {
    var i = Cn();
    $e.flags |= e, i.memoizedState = bo(1 | t, n, void 0, r === void 0 ? null : r);
  }
  function la(e, t, n, r) {
    var i = on();
    r = r === void 0 ? null : r;
    var o = void 0;
    if (rt !== null) {
      var s = rt.memoizedState;
      if (o = s.destroy, r !== null && Yu(r, s.deps)) {
        i.memoizedState = bo(t, n, o, r);
        return;
      }
    }
    $e.flags |= e, i.memoizedState = bo(1 | t, n, o, r);
  }
  function dd(e, t) {
    return ms(8390656, 8, e, t);
  }
  function Zu(e, t) {
    return la(2048, 8, e, t);
  }
  function Jh(e, t) {
    return la(4, 2, e, t);
  }
  function ep(e, t) {
    return la(4, 4, e, t);
  }
  function tp(e, t) {
    if (typeof t == "function") return e = e(), t(e), function() {
      t(null);
    };
    if (t != null) return e = e(), t.current = e, function() {
      t.current = null;
    };
  }
  function np(e, t, n) {
    return n = n != null ? n.concat([
      e
    ]) : null, la(4, 4, tp.bind(null, t, e), n);
  }
  function qu() {
  }
  function rp(e, t) {
    var n = on();
    t = t === void 0 ? null : t;
    var r = n.memoizedState;
    return r !== null && t !== null && Yu(t, r[1]) ? r[0] : (n.memoizedState = [
      e,
      t
    ], e);
  }
  function ip(e, t) {
    var n = on();
    t = t === void 0 ? null : t;
    var r = n.memoizedState;
    return r !== null && t !== null && Yu(t, r[1]) ? r[0] : (e = e(), n.memoizedState = [
      e,
      t
    ], e);
  }
  function op(e, t, n) {
    return Nr & 21 ? (Sn(n, t) || (n = ch(), $e.lanes |= n, Fr |= n, e.baseState = true), t) : (e.baseState && (e.baseState = false, Gt = true), e.memoizedState = n);
  }
  function gy(e, t) {
    var n = De;
    De = n !== 0 && 4 > n ? n : 4, e(true);
    var r = Wa.transition;
    Wa.transition = {};
    try {
      e(false), t();
    } finally {
      De = n, Wa.transition = r;
    }
  }
  function sp() {
    return on().memoizedState;
  }
  function my(e, t, n) {
    var r = pr(e);
    if (n = {
      lane: r,
      action: n,
      hasEagerState: false,
      eagerState: null,
      next: null
    }, ap(e)) lp(t, n);
    else if (n = $h(e, t, n, r), n !== null) {
      var i = Lt();
      En(n, e, r, i), up(n, t, r);
    }
  }
  function vy(e, t, n) {
    var r = pr(e), i = {
      lane: r,
      action: n,
      hasEagerState: false,
      eagerState: null,
      next: null
    };
    if (ap(e)) lp(t, i);
    else {
      var o = e.alternate;
      if (e.lanes === 0 && (o === null || o.lanes === 0) && (o = t.lastRenderedReducer, o !== null)) try {
        var s = t.lastRenderedState, a = o(s, n);
        if (i.hasEagerState = true, i.eagerState = a, Sn(a, s)) {
          var l = t.interleaved;
          l === null ? (i.next = i, ju(t)) : (i.next = l.next, l.next = i), t.interleaved = i;
          return;
        }
      } catch {
      } finally {
      }
      n = $h(e, t, i, r), n !== null && (i = Lt(), En(n, e, r, i), up(n, t, r));
    }
  }
  function ap(e) {
    var t = e.alternate;
    return e === $e || t !== null && t === $e;
  }
  function lp(e, t) {
    ro = Ms = true;
    var n = e.pending;
    n === null ? t.next = t : (t.next = n.next, n.next = t), e.pending = t;
  }
  function up(e, t, n) {
    if (n & 4194240) {
      var r = t.lanes;
      r &= e.pendingLanes, n |= r, t.lanes = n, Au(e, n);
    }
  }
  var $s = {
    readContext: rn,
    useCallback: St,
    useContext: St,
    useEffect: St,
    useImperativeHandle: St,
    useInsertionEffect: St,
    useLayoutEffect: St,
    useMemo: St,
    useReducer: St,
    useRef: St,
    useState: St,
    useDebugValue: St,
    useDeferredValue: St,
    useTransition: St,
    useMutableSource: St,
    useSyncExternalStore: St,
    useId: St,
    unstable_isNewReconciler: false
  }, yy = {
    readContext: rn,
    useCallback: function(e, t) {
      return Cn().memoizedState = [
        e,
        t === void 0 ? null : t
      ], e;
    },
    useContext: rn,
    useEffect: dd,
    useImperativeHandle: function(e, t, n) {
      return n = n != null ? n.concat([
        e
      ]) : null, ms(4194308, 4, tp.bind(null, t, e), n);
    },
    useLayoutEffect: function(e, t) {
      return ms(4194308, 4, e, t);
    },
    useInsertionEffect: function(e, t) {
      return ms(4, 2, e, t);
    },
    useMemo: function(e, t) {
      var n = Cn();
      return t = t === void 0 ? null : t, e = e(), n.memoizedState = [
        e,
        t
      ], e;
    },
    useReducer: function(e, t, n) {
      var r = Cn();
      return t = n !== void 0 ? n(t) : t, r.memoizedState = r.baseState = t, e = {
        pending: null,
        interleaved: null,
        lanes: 0,
        dispatch: null,
        lastRenderedReducer: e,
        lastRenderedState: t
      }, r.queue = e, e = e.dispatch = my.bind(null, $e, e), [
        r.memoizedState,
        e
      ];
    },
    useRef: function(e) {
      var t = Cn();
      return e = {
        current: e
      }, t.memoizedState = e;
    },
    useState: cd,
    useDebugValue: qu,
    useDeferredValue: function(e) {
      return Cn().memoizedState = e;
    },
    useTransition: function() {
      var e = cd(false), t = e[0];
      return e = gy.bind(null, e[1]), Cn().memoizedState = e, [
        t,
        e
      ];
    },
    useMutableSource: function() {
    },
    useSyncExternalStore: function(e, t, n) {
      var r = $e, i = Cn();
      if (Ue) {
        if (n === void 0) throw Error(W(407));
        n = n();
      } else {
        if (n = t(), dt === null) throw Error(W(349));
        Nr & 30 || Kh(r, t, n);
      }
      i.memoizedState = n;
      var o = {
        value: n,
        getSnapshot: t
      };
      return i.queue = o, dd(Qh.bind(null, r, o, e), [
        e
      ]), r.flags |= 2048, bo(9, Yh.bind(null, r, o, n, t), void 0, null), n;
    },
    useId: function() {
      var e = Cn(), t = dt.identifierPrefix;
      if (Ue) {
        var n = Mn, r = Bn;
        n = (r & ~(1 << 32 - wn(r) - 1)).toString(32) + n, t = ":" + t + "R" + n, n = _o++, 0 < n && (t += "H" + n.toString(32)), t += ":";
      } else n = py++, t = ":" + t + "r" + n.toString(32) + ":";
      return e.memoizedState = t;
    },
    unstable_isNewReconciler: false
  }, wy = {
    readContext: rn,
    useCallback: rp,
    useContext: rn,
    useEffect: Zu,
    useImperativeHandle: np,
    useInsertionEffect: Jh,
    useLayoutEffect: ep,
    useMemo: ip,
    useReducer: Va,
    useRef: qh,
    useState: function() {
      return Va(ko);
    },
    useDebugValue: qu,
    useDeferredValue: function(e) {
      var t = on();
      return op(t, rt.memoizedState, e);
    },
    useTransition: function() {
      var e = Va(ko)[0], t = on().memoizedState;
      return [
        e,
        t
      ];
    },
    useMutableSource: Wh,
    useSyncExternalStore: Vh,
    useId: sp,
    unstable_isNewReconciler: false
  }, Ey = {
    readContext: rn,
    useCallback: rp,
    useContext: rn,
    useEffect: Zu,
    useImperativeHandle: np,
    useInsertionEffect: Jh,
    useLayoutEffect: ep,
    useMemo: ip,
    useReducer: Ka,
    useRef: qh,
    useState: function() {
      return Ka(ko);
    },
    useDebugValue: qu,
    useDeferredValue: function(e) {
      var t = on();
      return rt === null ? t.memoizedState = e : op(t, rt.memoizedState, e);
    },
    useTransition: function() {
      var e = Ka(ko)[0], t = on().memoizedState;
      return [
        e,
        t
      ];
    },
    useMutableSource: Wh,
    useSyncExternalStore: Vh,
    useId: sp,
    unstable_isNewReconciler: false
  };
  function gn(e, t) {
    if (e && e.defaultProps) {
      t = je({}, t), e = e.defaultProps;
      for (var n in e) t[n] === void 0 && (t[n] = e[n]);
      return t;
    }
    return t;
  }
  function Wl(e, t, n, r) {
    t = e.memoizedState, n = n(r, t), n = n == null ? t : je({}, t, n), e.memoizedState = n, e.lanes === 0 && (e.updateQueue.baseState = n);
  }
  var ua = {
    isMounted: function(e) {
      return (e = e._reactInternals) ? Gr(e) === e : false;
    },
    enqueueSetState: function(e, t, n) {
      e = e._reactInternals;
      var r = Lt(), i = pr(e), o = $n(r, i);
      o.payload = t, n != null && (o.callback = n), t = fr(e, o, i), t !== null && (En(t, e, i, r), ps(t, e, i));
    },
    enqueueReplaceState: function(e, t, n) {
      e = e._reactInternals;
      var r = Lt(), i = pr(e), o = $n(r, i);
      o.tag = 1, o.payload = t, n != null && (o.callback = n), t = fr(e, o, i), t !== null && (En(t, e, i, r), ps(t, e, i));
    },
    enqueueForceUpdate: function(e, t) {
      e = e._reactInternals;
      var n = Lt(), r = pr(e), i = $n(n, r);
      i.tag = 2, t != null && (i.callback = t), t = fr(e, i, r), t !== null && (En(t, e, r, n), ps(t, e, r));
    }
  };
  function fd(e, t, n, r, i, o, s) {
    return e = e.stateNode, typeof e.shouldComponentUpdate == "function" ? e.shouldComponentUpdate(r, o, s) : t.prototype && t.prototype.isPureReactComponent ? !mo(n, r) || !mo(i, o) : true;
  }
  function cp(e, t, n) {
    var r = false, i = vr, o = t.contextType;
    return typeof o == "object" && o !== null ? o = rn(o) : (i = Bt(t) ? Dr : xt.current, r = t.contextTypes, o = (r = r != null) ? ci(e, i) : vr), t = new t(n, o), e.memoizedState = t.state !== null && t.state !== void 0 ? t.state : null, t.updater = ua, e.stateNode = t, t._reactInternals = e, r && (e = e.stateNode, e.__reactInternalMemoizedUnmaskedChildContext = i, e.__reactInternalMemoizedMaskedChildContext = o), t;
  }
  function hd(e, t, n, r) {
    e = t.state, typeof t.componentWillReceiveProps == "function" && t.componentWillReceiveProps(n, r), typeof t.UNSAFE_componentWillReceiveProps == "function" && t.UNSAFE_componentWillReceiveProps(n, r), t.state !== e && ua.enqueueReplaceState(t, t.state, null);
  }
  function Vl(e, t, n, r) {
    var i = e.stateNode;
    i.props = n, i.state = e.memoizedState, i.refs = {}, Hu(e);
    var o = t.contextType;
    typeof o == "object" && o !== null ? i.context = rn(o) : (o = Bt(t) ? Dr : xt.current, i.context = ci(e, o)), i.state = e.memoizedState, o = t.getDerivedStateFromProps, typeof o == "function" && (Wl(e, t, o, n), i.state = e.memoizedState), typeof t.getDerivedStateFromProps == "function" || typeof i.getSnapshotBeforeUpdate == "function" || typeof i.UNSAFE_componentWillMount != "function" && typeof i.componentWillMount != "function" || (t = i.state, typeof i.componentWillMount == "function" && i.componentWillMount(), typeof i.UNSAFE_componentWillMount == "function" && i.UNSAFE_componentWillMount(), t !== i.state && ua.enqueueReplaceState(i, i.state, null), Us(e, n, i, r), i.state = e.memoizedState), typeof i.componentDidMount == "function" && (e.flags |= 4194308);
  }
  function pi(e, t) {
    try {
      var n = "", r = t;
      do
        n += Ym(r), r = r.return;
      while (r);
      var i = n;
    } catch (o) {
      i = `
Error generating stack: ` + o.message + `
` + o.stack;
    }
    return {
      value: e,
      source: t,
      stack: i,
      digest: null
    };
  }
  function Ya(e, t, n) {
    return {
      value: e,
      source: null,
      stack: n ?? null,
      digest: t ?? null
    };
  }
  function Kl(e, t) {
    try {
      console.error(t.value);
    } catch (n) {
      setTimeout(function() {
        throw n;
      });
    }
  }
  var Sy = typeof WeakMap == "function" ? WeakMap : Map;
  function dp(e, t, n) {
    n = $n(-1, n), n.tag = 3, n.payload = {
      element: null
    };
    var r = t.value;
    return n.callback = function() {
      Hs || (Hs = true, ru = r), Kl(e, t);
    }, n;
  }
  function fp(e, t, n) {
    n = $n(-1, n), n.tag = 3;
    var r = e.type.getDerivedStateFromError;
    if (typeof r == "function") {
      var i = t.value;
      n.payload = function() {
        return r(i);
      }, n.callback = function() {
        Kl(e, t);
      };
    }
    var o = e.stateNode;
    return o !== null && typeof o.componentDidCatch == "function" && (n.callback = function() {
      Kl(e, t), typeof r != "function" && (hr === null ? hr = /* @__PURE__ */ new Set([
        this
      ]) : hr.add(this));
      var s = t.stack;
      this.componentDidCatch(t.value, {
        componentStack: s !== null ? s : ""
      });
    }), n;
  }
  function pd(e, t, n) {
    var r = e.pingCache;
    if (r === null) {
      r = e.pingCache = new Sy();
      var i = /* @__PURE__ */ new Set();
      r.set(t, i);
    } else i = r.get(t), i === void 0 && (i = /* @__PURE__ */ new Set(), r.set(t, i));
    i.has(n) || (i.add(n), e = Fy.bind(null, e, t, n), t.then(e, e));
  }
  function gd(e) {
    do {
      var t;
      if ((t = e.tag === 13) && (t = e.memoizedState, t = t !== null ? t.dehydrated !== null : true), t) return e;
      e = e.return;
    } while (e !== null);
    return null;
  }
  function md(e, t, n, r, i) {
    return e.mode & 1 ? (e.flags |= 65536, e.lanes = i, e) : (e === t ? e.flags |= 65536 : (e.flags |= 128, n.flags |= 131072, n.flags &= -52805, n.tag === 1 && (n.alternate === null ? n.tag = 17 : (t = $n(-1, 1), t.tag = 2, fr(n, t, 1))), n.lanes |= 1), e);
  }
  var _y = Yn.ReactCurrentOwner, Gt = false;
  function At(e, t, n, r) {
    t.child = e === null ? Mh(t, null, n, r) : fi(t, e.child, n, r);
  }
  function vd(e, t, n, r, i) {
    n = n.render;
    var o = t.ref;
    return oi(t, i), r = Qu(e, t, n, r, o, i), n = Xu(), e !== null && !Gt ? (t.updateQueue = e.updateQueue, t.flags &= -2053, e.lanes &= ~i, Kn(e, t, i)) : (Ue && n && Ou(t), t.flags |= 1, At(e, t, r, i), t.child);
  }
  function yd(e, t, n, r, i) {
    if (e === null) {
      var o = n.type;
      return typeof o == "function" && !sc(o) && o.defaultProps === void 0 && n.compare === null && n.defaultProps === void 0 ? (t.tag = 15, t.type = o, hp(e, t, o, r, i)) : (e = Es(n.type, null, r, t, t.mode, i), e.ref = t.ref, e.return = t, t.child = e);
    }
    if (o = e.child, !(e.lanes & i)) {
      var s = o.memoizedProps;
      if (n = n.compare, n = n !== null ? n : mo, n(s, r) && e.ref === t.ref) return Kn(e, t, i);
    }
    return t.flags |= 1, e = gr(o, r), e.ref = t.ref, e.return = t, t.child = e;
  }
  function hp(e, t, n, r, i) {
    if (e !== null) {
      var o = e.memoizedProps;
      if (mo(o, r) && e.ref === t.ref) if (Gt = false, t.pendingProps = r = o, (e.lanes & i) !== 0) e.flags & 131072 && (Gt = true);
      else return t.lanes = e.lanes, Kn(e, t, i);
    }
    return Yl(e, t, n, r, i);
  }
  function pp(e, t, n) {
    var r = t.pendingProps, i = r.children, o = e !== null ? e.memoizedState : null;
    if (r.mode === "hidden") if (!(t.mode & 1)) t.memoizedState = {
      baseLanes: 0,
      cachePool: null,
      transitions: null
    }, Fe(ei, jt), jt |= n;
    else {
      if (!(n & 1073741824)) return e = o !== null ? o.baseLanes | n : n, t.lanes = t.childLanes = 1073741824, t.memoizedState = {
        baseLanes: e,
        cachePool: null,
        transitions: null
      }, t.updateQueue = null, Fe(ei, jt), jt |= e, null;
      t.memoizedState = {
        baseLanes: 0,
        cachePool: null,
        transitions: null
      }, r = o !== null ? o.baseLanes : n, Fe(ei, jt), jt |= r;
    }
    else o !== null ? (r = o.baseLanes | n, t.memoizedState = null) : r = n, Fe(ei, jt), jt |= r;
    return At(e, t, i, n), t.child;
  }
  function gp(e, t) {
    var n = t.ref;
    (e === null && n !== null || e !== null && e.ref !== n) && (t.flags |= 512, t.flags |= 2097152);
  }
  function Yl(e, t, n, r, i) {
    var o = Bt(n) ? Dr : xt.current;
    return o = ci(t, o), oi(t, i), n = Qu(e, t, n, r, o, i), r = Xu(), e !== null && !Gt ? (t.updateQueue = e.updateQueue, t.flags &= -2053, e.lanes &= ~i, Kn(e, t, i)) : (Ue && r && Ou(t), t.flags |= 1, At(e, t, n, i), t.child);
  }
  function wd(e, t, n, r, i) {
    if (Bt(n)) {
      var o = true;
      Ns(t);
    } else o = false;
    if (oi(t, i), t.stateNode === null) vs(e, t), cp(t, n, r), Vl(t, n, r, i), r = true;
    else if (e === null) {
      var s = t.stateNode, a = t.memoizedProps;
      s.props = a;
      var l = s.context, c = n.contextType;
      typeof c == "object" && c !== null ? c = rn(c) : (c = Bt(n) ? Dr : xt.current, c = ci(t, c));
      var h = n.getDerivedStateFromProps, f = typeof h == "function" || typeof s.getSnapshotBeforeUpdate == "function";
      f || typeof s.UNSAFE_componentWillReceiveProps != "function" && typeof s.componentWillReceiveProps != "function" || (a !== r || l !== c) && hd(t, s, r, c), rr = false;
      var p = t.memoizedState;
      s.state = p, Us(t, r, s, i), l = t.memoizedState, a !== r || p !== l || Ut.current || rr ? (typeof h == "function" && (Wl(t, n, h, r), l = t.memoizedState), (a = rr || fd(t, n, a, r, p, l, c)) ? (f || typeof s.UNSAFE_componentWillMount != "function" && typeof s.componentWillMount != "function" || (typeof s.componentWillMount == "function" && s.componentWillMount(), typeof s.UNSAFE_componentWillMount == "function" && s.UNSAFE_componentWillMount()), typeof s.componentDidMount == "function" && (t.flags |= 4194308)) : (typeof s.componentDidMount == "function" && (t.flags |= 4194308), t.memoizedProps = r, t.memoizedState = l), s.props = r, s.state = l, s.context = c, r = a) : (typeof s.componentDidMount == "function" && (t.flags |= 4194308), r = false);
    } else {
      s = t.stateNode, jh(e, t), a = t.memoizedProps, c = t.type === t.elementType ? a : gn(t.type, a), s.props = c, f = t.pendingProps, p = s.context, l = n.contextType, typeof l == "object" && l !== null ? l = rn(l) : (l = Bt(n) ? Dr : xt.current, l = ci(t, l));
      var y = n.getDerivedStateFromProps;
      (h = typeof y == "function" || typeof s.getSnapshotBeforeUpdate == "function") || typeof s.UNSAFE_componentWillReceiveProps != "function" && typeof s.componentWillReceiveProps != "function" || (a !== f || p !== l) && hd(t, s, r, l), rr = false, p = t.memoizedState, s.state = p, Us(t, r, s, i);
      var k = t.memoizedState;
      a !== f || p !== k || Ut.current || rr ? (typeof y == "function" && (Wl(t, n, y, r), k = t.memoizedState), (c = rr || fd(t, n, c, r, p, k, l) || false) ? (h || typeof s.UNSAFE_componentWillUpdate != "function" && typeof s.componentWillUpdate != "function" || (typeof s.componentWillUpdate == "function" && s.componentWillUpdate(r, k, l), typeof s.UNSAFE_componentWillUpdate == "function" && s.UNSAFE_componentWillUpdate(r, k, l)), typeof s.componentDidUpdate == "function" && (t.flags |= 4), typeof s.getSnapshotBeforeUpdate == "function" && (t.flags |= 1024)) : (typeof s.componentDidUpdate != "function" || a === e.memoizedProps && p === e.memoizedState || (t.flags |= 4), typeof s.getSnapshotBeforeUpdate != "function" || a === e.memoizedProps && p === e.memoizedState || (t.flags |= 1024), t.memoizedProps = r, t.memoizedState = k), s.props = r, s.state = k, s.context = l, r = c) : (typeof s.componentDidUpdate != "function" || a === e.memoizedProps && p === e.memoizedState || (t.flags |= 4), typeof s.getSnapshotBeforeUpdate != "function" || a === e.memoizedProps && p === e.memoizedState || (t.flags |= 1024), r = false);
    }
    return Ql(e, t, n, r, o, i);
  }
  function Ql(e, t, n, r, i, o) {
    gp(e, t);
    var s = (t.flags & 128) !== 0;
    if (!r && !s) return i && id(t, n, false), Kn(e, t, o);
    r = t.stateNode, _y.current = t;
    var a = s && typeof n.getDerivedStateFromError != "function" ? null : r.render();
    return t.flags |= 1, e !== null && s ? (t.child = fi(t, e.child, null, o), t.child = fi(t, null, a, o)) : At(e, t, a, o), t.memoizedState = r.state, i && id(t, n, true), t.child;
  }
  function mp(e) {
    var t = e.stateNode;
    t.pendingContext ? rd(e, t.pendingContext, t.pendingContext !== t.context) : t.context && rd(e, t.context, false), Wu(e, t.containerInfo);
  }
  function Ed(e, t, n, r, i) {
    return di(), Uu(i), t.flags |= 256, At(e, t, n, r), t.child;
  }
  var Xl = {
    dehydrated: null,
    treeContext: null,
    retryLane: 0
  };
  function Zl(e) {
    return {
      baseLanes: e,
      cachePool: null,
      transitions: null
    };
  }
  function vp(e, t, n) {
    var r = t.pendingProps, i = Me.current, o = false, s = (t.flags & 128) !== 0, a;
    if ((a = s) || (a = e !== null && e.memoizedState === null ? false : (i & 2) !== 0), a ? (o = true, t.flags &= -129) : (e === null || e.memoizedState !== null) && (i |= 1), Fe(Me, i & 1), e === null) return jl(t), e = t.memoizedState, e !== null && (e = e.dehydrated, e !== null) ? (t.mode & 1 ? e.data === "$!" ? t.lanes = 8 : t.lanes = 1073741824 : t.lanes = 1, null) : (s = r.children, e = r.fallback, o ? (r = t.mode, o = t.child, s = {
      mode: "hidden",
      children: s
    }, !(r & 1) && o !== null ? (o.childLanes = 0, o.pendingProps = s) : o = fa(s, r, 0, null), e = Ir(e, r, n, null), o.return = t, e.return = t, o.sibling = e, t.child = o, t.child.memoizedState = Zl(n), t.memoizedState = Xl, e) : Ju(t, s));
    if (i = e.memoizedState, i !== null && (a = i.dehydrated, a !== null)) return ky(e, t, s, r, a, i, n);
    if (o) {
      o = r.fallback, s = t.mode, i = e.child, a = i.sibling;
      var l = {
        mode: "hidden",
        children: r.children
      };
      return !(s & 1) && t.child !== i ? (r = t.child, r.childLanes = 0, r.pendingProps = l, t.deletions = null) : (r = gr(i, l), r.subtreeFlags = i.subtreeFlags & 14680064), a !== null ? o = gr(a, o) : (o = Ir(o, s, n, null), o.flags |= 2), o.return = t, r.return = t, r.sibling = o, t.child = r, r = o, o = t.child, s = e.child.memoizedState, s = s === null ? Zl(n) : {
        baseLanes: s.baseLanes | n,
        cachePool: null,
        transitions: s.transitions
      }, o.memoizedState = s, o.childLanes = e.childLanes & ~n, t.memoizedState = Xl, r;
    }
    return o = e.child, e = o.sibling, r = gr(o, {
      mode: "visible",
      children: r.children
    }), !(t.mode & 1) && (r.lanes = n), r.return = t, r.sibling = null, e !== null && (n = t.deletions, n === null ? (t.deletions = [
      e
    ], t.flags |= 16) : n.push(e)), t.child = r, t.memoizedState = null, r;
  }
  function Ju(e, t) {
    return t = fa({
      mode: "visible",
      children: t
    }, e.mode, 0, null), t.return = e, e.child = t;
  }
  function Xo(e, t, n, r) {
    return r !== null && Uu(r), fi(t, e.child, null, n), e = Ju(t, t.pendingProps.children), e.flags |= 2, t.memoizedState = null, e;
  }
  function ky(e, t, n, r, i, o, s) {
    if (n) return t.flags & 256 ? (t.flags &= -257, r = Ya(Error(W(422))), Xo(e, t, s, r)) : t.memoizedState !== null ? (t.child = e.child, t.flags |= 128, null) : (o = r.fallback, i = t.mode, r = fa({
      mode: "visible",
      children: r.children
    }, i, 0, null), o = Ir(o, i, s, null), o.flags |= 2, r.return = t, o.return = t, r.sibling = o, t.child = r, t.mode & 1 && fi(t, e.child, null, s), t.child.memoizedState = Zl(s), t.memoizedState = Xl, o);
    if (!(t.mode & 1)) return Xo(e, t, s, null);
    if (i.data === "$!") {
      if (r = i.nextSibling && i.nextSibling.dataset, r) var a = r.dgst;
      return r = a, o = Error(W(419)), r = Ya(o, r, void 0), Xo(e, t, s, r);
    }
    if (a = (s & e.childLanes) !== 0, Gt || a) {
      if (r = dt, r !== null) {
        switch (s & -s) {
          case 4:
            i = 2;
            break;
          case 16:
            i = 8;
            break;
          case 64:
          case 128:
          case 256:
          case 512:
          case 1024:
          case 2048:
          case 4096:
          case 8192:
          case 16384:
          case 32768:
          case 65536:
          case 131072:
          case 262144:
          case 524288:
          case 1048576:
          case 2097152:
          case 4194304:
          case 8388608:
          case 16777216:
          case 33554432:
          case 67108864:
            i = 32;
            break;
          case 536870912:
            i = 268435456;
            break;
          default:
            i = 0;
        }
        i = i & (r.suspendedLanes | s) ? 0 : i, i !== 0 && i !== o.retryLane && (o.retryLane = i, Vn(e, i), En(r, e, i, -1));
      }
      return oc(), r = Ya(Error(W(421))), Xo(e, t, s, r);
    }
    return i.data === "$?" ? (t.flags |= 128, t.child = e.child, t = zy.bind(null, e), i._reactRetry = t, null) : (e = o.treeContext, Ht = dr(i.nextSibling), Wt = t, Ue = true, vn = null, e !== null && (qt[Jt++] = Bn, qt[Jt++] = Mn, qt[Jt++] = Pr, Bn = e.id, Mn = e.overflow, Pr = t), t = Ju(t, r.children), t.flags |= 4096, t);
  }
  function Sd(e, t, n) {
    e.lanes |= t;
    var r = e.alternate;
    r !== null && (r.lanes |= t), Hl(e.return, t, n);
  }
  function Qa(e, t, n, r, i) {
    var o = e.memoizedState;
    o === null ? e.memoizedState = {
      isBackwards: t,
      rendering: null,
      renderingStartTime: 0,
      last: r,
      tail: n,
      tailMode: i
    } : (o.isBackwards = t, o.rendering = null, o.renderingStartTime = 0, o.last = r, o.tail = n, o.tailMode = i);
  }
  function yp(e, t, n) {
    var r = t.pendingProps, i = r.revealOrder, o = r.tail;
    if (At(e, t, r.children, n), r = Me.current, r & 2) r = r & 1 | 2, t.flags |= 128;
    else {
      if (e !== null && e.flags & 128) e: for (e = t.child; e !== null; ) {
        if (e.tag === 13) e.memoizedState !== null && Sd(e, n, t);
        else if (e.tag === 19) Sd(e, n, t);
        else if (e.child !== null) {
          e.child.return = e, e = e.child;
          continue;
        }
        if (e === t) break e;
        for (; e.sibling === null; ) {
          if (e.return === null || e.return === t) break e;
          e = e.return;
        }
        e.sibling.return = e.return, e = e.sibling;
      }
      r &= 1;
    }
    if (Fe(Me, r), !(t.mode & 1)) t.memoizedState = null;
    else switch (i) {
      case "forwards":
        for (n = t.child, i = null; n !== null; ) e = n.alternate, e !== null && Bs(e) === null && (i = n), n = n.sibling;
        n = i, n === null ? (i = t.child, t.child = null) : (i = n.sibling, n.sibling = null), Qa(t, false, i, n, o);
        break;
      case "backwards":
        for (n = null, i = t.child, t.child = null; i !== null; ) {
          if (e = i.alternate, e !== null && Bs(e) === null) {
            t.child = i;
            break;
          }
          e = i.sibling, i.sibling = n, n = i, i = e;
        }
        Qa(t, true, n, null, o);
        break;
      case "together":
        Qa(t, false, null, null, void 0);
        break;
      default:
        t.memoizedState = null;
    }
    return t.child;
  }
  function vs(e, t) {
    !(t.mode & 1) && e !== null && (e.alternate = null, t.alternate = null, t.flags |= 2);
  }
  function Kn(e, t, n) {
    if (e !== null && (t.dependencies = e.dependencies), Fr |= t.lanes, !(n & t.childLanes)) return null;
    if (e !== null && t.child !== e.child) throw Error(W(153));
    if (t.child !== null) {
      for (e = t.child, n = gr(e, e.pendingProps), t.child = n, n.return = t; e.sibling !== null; ) e = e.sibling, n = n.sibling = gr(e, e.pendingProps), n.return = t;
      n.sibling = null;
    }
    return t.child;
  }
  function by(e, t, n) {
    switch (t.tag) {
      case 3:
        mp(t), di();
        break;
      case 5:
        Hh(t);
        break;
      case 1:
        Bt(t.type) && Ns(t);
        break;
      case 4:
        Wu(t, t.stateNode.containerInfo);
        break;
      case 10:
        var r = t.type._context, i = t.memoizedProps.value;
        Fe(Os, r._currentValue), r._currentValue = i;
        break;
      case 13:
        if (r = t.memoizedState, r !== null) return r.dehydrated !== null ? (Fe(Me, Me.current & 1), t.flags |= 128, null) : n & t.child.childLanes ? vp(e, t, n) : (Fe(Me, Me.current & 1), e = Kn(e, t, n), e !== null ? e.sibling : null);
        Fe(Me, Me.current & 1);
        break;
      case 19:
        if (r = (n & t.childLanes) !== 0, e.flags & 128) {
          if (r) return yp(e, t, n);
          t.flags |= 128;
        }
        if (i = t.memoizedState, i !== null && (i.rendering = null, i.tail = null, i.lastEffect = null), Fe(Me, Me.current), r) break;
        return null;
      case 22:
      case 23:
        return t.lanes = 0, pp(e, t, n);
    }
    return Kn(e, t, n);
  }
  var wp, ql, Ep, Sp;
  wp = function(e, t) {
    for (var n = t.child; n !== null; ) {
      if (n.tag === 5 || n.tag === 6) e.appendChild(n.stateNode);
      else if (n.tag !== 4 && n.child !== null) {
        n.child.return = n, n = n.child;
        continue;
      }
      if (n === t) break;
      for (; n.sibling === null; ) {
        if (n.return === null || n.return === t) return;
        n = n.return;
      }
      n.sibling.return = n.return, n = n.sibling;
    }
  };
  ql = function() {
  };
  Ep = function(e, t, n, r) {
    var i = e.memoizedProps;
    if (i !== r) {
      e = t.stateNode, Ar(Ln.current);
      var o = null;
      switch (n) {
        case "input":
          i = El(e, i), r = El(e, r), o = [];
          break;
        case "select":
          i = je({}, i, {
            value: void 0
          }), r = je({}, r, {
            value: void 0
          }), o = [];
          break;
        case "textarea":
          i = kl(e, i), r = kl(e, r), o = [];
          break;
        default:
          typeof i.onClick != "function" && typeof r.onClick == "function" && (e.onclick = Ds);
      }
      xl(n, r);
      var s;
      n = null;
      for (c in i) if (!r.hasOwnProperty(c) && i.hasOwnProperty(c) && i[c] != null) if (c === "style") {
        var a = i[c];
        for (s in a) a.hasOwnProperty(s) && (n || (n = {}), n[s] = "");
      } else c !== "dangerouslySetInnerHTML" && c !== "children" && c !== "suppressContentEditableWarning" && c !== "suppressHydrationWarning" && c !== "autoFocus" && (lo.hasOwnProperty(c) ? o || (o = []) : (o = o || []).push(c, null));
      for (c in r) {
        var l = r[c];
        if (a = i == null ? void 0 : i[c], r.hasOwnProperty(c) && l !== a && (l != null || a != null)) if (c === "style") if (a) {
          for (s in a) !a.hasOwnProperty(s) || l && l.hasOwnProperty(s) || (n || (n = {}), n[s] = "");
          for (s in l) l.hasOwnProperty(s) && a[s] !== l[s] && (n || (n = {}), n[s] = l[s]);
        } else n || (o || (o = []), o.push(c, n)), n = l;
        else c === "dangerouslySetInnerHTML" ? (l = l ? l.__html : void 0, a = a ? a.__html : void 0, l != null && a !== l && (o = o || []).push(c, l)) : c === "children" ? typeof l != "string" && typeof l != "number" || (o = o || []).push(c, "" + l) : c !== "suppressContentEditableWarning" && c !== "suppressHydrationWarning" && (lo.hasOwnProperty(c) ? (l != null && c === "onScroll" && Oe("scroll", e), o || a === l || (o = [])) : (o = o || []).push(c, l));
      }
      n && (o = o || []).push("style", n);
      var c = o;
      (t.updateQueue = c) && (t.flags |= 4);
    }
  };
  Sp = function(e, t, n, r) {
    n !== r && (t.flags |= 4);
  };
  function Fi(e, t) {
    if (!Ue) switch (e.tailMode) {
      case "hidden":
        t = e.tail;
        for (var n = null; t !== null; ) t.alternate !== null && (n = t), t = t.sibling;
        n === null ? e.tail = null : n.sibling = null;
        break;
      case "collapsed":
        n = e.tail;
        for (var r = null; n !== null; ) n.alternate !== null && (r = n), n = n.sibling;
        r === null ? t || e.tail === null ? e.tail = null : e.tail.sibling = null : r.sibling = null;
    }
  }
  function _t(e) {
    var t = e.alternate !== null && e.alternate.child === e.child, n = 0, r = 0;
    if (t) for (var i = e.child; i !== null; ) n |= i.lanes | i.childLanes, r |= i.subtreeFlags & 14680064, r |= i.flags & 14680064, i.return = e, i = i.sibling;
    else for (i = e.child; i !== null; ) n |= i.lanes | i.childLanes, r |= i.subtreeFlags, r |= i.flags, i.return = e, i = i.sibling;
    return e.subtreeFlags |= r, e.childLanes = n, t;
  }
  function xy(e, t, n) {
    var r = t.pendingProps;
    switch (Gu(t), t.tag) {
      case 2:
      case 16:
      case 15:
      case 0:
      case 11:
      case 7:
      case 8:
      case 12:
      case 9:
      case 14:
        return _t(t), null;
      case 1:
        return Bt(t.type) && Ps(), _t(t), null;
      case 3:
        return r = t.stateNode, hi(), Ge(Ut), Ge(xt), Ku(), r.pendingContext && (r.context = r.pendingContext, r.pendingContext = null), (e === null || e.child === null) && (Yo(t) ? t.flags |= 4 : e === null || e.memoizedState.isDehydrated && !(t.flags & 256) || (t.flags |= 1024, vn !== null && (su(vn), vn = null))), ql(e, t), _t(t), null;
      case 5:
        Vu(t);
        var i = Ar(So.current);
        if (n = t.type, e !== null && t.stateNode != null) Ep(e, t, n, r, i), e.ref !== t.ref && (t.flags |= 512, t.flags |= 2097152);
        else {
          if (!r) {
            if (t.stateNode === null) throw Error(W(166));
            return _t(t), null;
          }
          if (e = Ar(Ln.current), Yo(t)) {
            r = t.stateNode, n = t.type;
            var o = t.memoizedProps;
            switch (r[Tn] = t, r[wo] = o, e = (t.mode & 1) !== 0, n) {
              case "dialog":
                Oe("cancel", r), Oe("close", r);
                break;
              case "iframe":
              case "object":
              case "embed":
                Oe("load", r);
                break;
              case "video":
              case "audio":
                for (i = 0; i < Xi.length; i++) Oe(Xi[i], r);
                break;
              case "source":
                Oe("error", r);
                break;
              case "img":
              case "image":
              case "link":
                Oe("error", r), Oe("load", r);
                break;
              case "details":
                Oe("toggle", r);
                break;
              case "input":
                Lc(r, o), Oe("invalid", r);
                break;
              case "select":
                r._wrapperState = {
                  wasMultiple: !!o.multiple
                }, Oe("invalid", r);
                break;
              case "textarea":
                Dc(r, o), Oe("invalid", r);
            }
            xl(n, o), i = null;
            for (var s in o) if (o.hasOwnProperty(s)) {
              var a = o[s];
              s === "children" ? typeof a == "string" ? r.textContent !== a && (o.suppressHydrationWarning !== true && Ko(r.textContent, a, e), i = [
                "children",
                a
              ]) : typeof a == "number" && r.textContent !== "" + a && (o.suppressHydrationWarning !== true && Ko(r.textContent, a, e), i = [
                "children",
                "" + a
              ]) : lo.hasOwnProperty(s) && a != null && s === "onScroll" && Oe("scroll", r);
            }
            switch (n) {
              case "input":
                Uo(r), Ic(r, o, true);
                break;
              case "textarea":
                Uo(r), Pc(r);
                break;
              case "select":
              case "option":
                break;
              default:
                typeof o.onClick == "function" && (r.onclick = Ds);
            }
            r = i, t.updateQueue = r, r !== null && (t.flags |= 4);
          } else {
            s = i.nodeType === 9 ? i : i.ownerDocument, e === "http://www.w3.org/1999/xhtml" && (e = Qf(n)), e === "http://www.w3.org/1999/xhtml" ? n === "script" ? (e = s.createElement("div"), e.innerHTML = "<script><\/script>", e = e.removeChild(e.firstChild)) : typeof r.is == "string" ? e = s.createElement(n, {
              is: r.is
            }) : (e = s.createElement(n), n === "select" && (s = e, r.multiple ? s.multiple = true : r.size && (s.size = r.size))) : e = s.createElementNS(e, n), e[Tn] = t, e[wo] = r, wp(e, t, false, false), t.stateNode = e;
            e: {
              switch (s = Cl(n, r), n) {
                case "dialog":
                  Oe("cancel", e), Oe("close", e), i = r;
                  break;
                case "iframe":
                case "object":
                case "embed":
                  Oe("load", e), i = r;
                  break;
                case "video":
                case "audio":
                  for (i = 0; i < Xi.length; i++) Oe(Xi[i], e);
                  i = r;
                  break;
                case "source":
                  Oe("error", e), i = r;
                  break;
                case "img":
                case "image":
                case "link":
                  Oe("error", e), Oe("load", e), i = r;
                  break;
                case "details":
                  Oe("toggle", e), i = r;
                  break;
                case "input":
                  Lc(e, r), i = El(e, r), Oe("invalid", e);
                  break;
                case "option":
                  i = r;
                  break;
                case "select":
                  e._wrapperState = {
                    wasMultiple: !!r.multiple
                  }, i = je({}, r, {
                    value: void 0
                  }), Oe("invalid", e);
                  break;
                case "textarea":
                  Dc(e, r), i = kl(e, r), Oe("invalid", e);
                  break;
                default:
                  i = r;
              }
              xl(n, i), a = i;
              for (o in a) if (a.hasOwnProperty(o)) {
                var l = a[o];
                o === "style" ? qf(e, l) : o === "dangerouslySetInnerHTML" ? (l = l ? l.__html : void 0, l != null && Xf(e, l)) : o === "children" ? typeof l == "string" ? (n !== "textarea" || l !== "") && uo(e, l) : typeof l == "number" && uo(e, "" + l) : o !== "suppressContentEditableWarning" && o !== "suppressHydrationWarning" && o !== "autoFocus" && (lo.hasOwnProperty(o) ? l != null && o === "onScroll" && Oe("scroll", e) : l != null && ku(e, o, l, s));
              }
              switch (n) {
                case "input":
                  Uo(e), Ic(e, r, false);
                  break;
                case "textarea":
                  Uo(e), Pc(e);
                  break;
                case "option":
                  r.value != null && e.setAttribute("value", "" + mr(r.value));
                  break;
                case "select":
                  e.multiple = !!r.multiple, o = r.value, o != null ? ti(e, !!r.multiple, o, false) : r.defaultValue != null && ti(e, !!r.multiple, r.defaultValue, true);
                  break;
                default:
                  typeof i.onClick == "function" && (e.onclick = Ds);
              }
              switch (n) {
                case "button":
                case "input":
                case "select":
                case "textarea":
                  r = !!r.autoFocus;
                  break e;
                case "img":
                  r = true;
                  break e;
                default:
                  r = false;
              }
            }
            r && (t.flags |= 4);
          }
          t.ref !== null && (t.flags |= 512, t.flags |= 2097152);
        }
        return _t(t), null;
      case 6:
        if (e && t.stateNode != null) Sp(e, t, e.memoizedProps, r);
        else {
          if (typeof r != "string" && t.stateNode === null) throw Error(W(166));
          if (n = Ar(So.current), Ar(Ln.current), Yo(t)) {
            if (r = t.stateNode, n = t.memoizedProps, r[Tn] = t, (o = r.nodeValue !== n) && (e = Wt, e !== null)) switch (e.tag) {
              case 3:
                Ko(r.nodeValue, n, (e.mode & 1) !== 0);
                break;
              case 5:
                e.memoizedProps.suppressHydrationWarning !== true && Ko(r.nodeValue, n, (e.mode & 1) !== 0);
            }
            o && (t.flags |= 4);
          } else r = (n.nodeType === 9 ? n : n.ownerDocument).createTextNode(r), r[Tn] = t, t.stateNode = r;
        }
        return _t(t), null;
      case 13:
        if (Ge(Me), r = t.memoizedState, e === null || e.memoizedState !== null && e.memoizedState.dehydrated !== null) {
          if (Ue && Ht !== null && t.mode & 1 && !(t.flags & 128)) Uh(), di(), t.flags |= 98560, o = false;
          else if (o = Yo(t), r !== null && r.dehydrated !== null) {
            if (e === null) {
              if (!o) throw Error(W(318));
              if (o = t.memoizedState, o = o !== null ? o.dehydrated : null, !o) throw Error(W(317));
              o[Tn] = t;
            } else di(), !(t.flags & 128) && (t.memoizedState = null), t.flags |= 4;
            _t(t), o = false;
          } else vn !== null && (su(vn), vn = null), o = true;
          if (!o) return t.flags & 65536 ? t : null;
        }
        return t.flags & 128 ? (t.lanes = n, t) : (r = r !== null, r !== (e !== null && e.memoizedState !== null) && r && (t.child.flags |= 8192, t.mode & 1 && (e === null || Me.current & 1 ? ot === 0 && (ot = 3) : oc())), t.updateQueue !== null && (t.flags |= 4), _t(t), null);
      case 4:
        return hi(), ql(e, t), e === null && vo(t.stateNode.containerInfo), _t(t), null;
      case 10:
        return $u(t.type._context), _t(t), null;
      case 17:
        return Bt(t.type) && Ps(), _t(t), null;
      case 19:
        if (Ge(Me), o = t.memoizedState, o === null) return _t(t), null;
        if (r = (t.flags & 128) !== 0, s = o.rendering, s === null) if (r) Fi(o, false);
        else {
          if (ot !== 0 || e !== null && e.flags & 128) for (e = t.child; e !== null; ) {
            if (s = Bs(e), s !== null) {
              for (t.flags |= 128, Fi(o, false), r = s.updateQueue, r !== null && (t.updateQueue = r, t.flags |= 4), t.subtreeFlags = 0, r = n, n = t.child; n !== null; ) o = n, e = r, o.flags &= 14680066, s = o.alternate, s === null ? (o.childLanes = 0, o.lanes = e, o.child = null, o.subtreeFlags = 0, o.memoizedProps = null, o.memoizedState = null, o.updateQueue = null, o.dependencies = null, o.stateNode = null) : (o.childLanes = s.childLanes, o.lanes = s.lanes, o.child = s.child, o.subtreeFlags = 0, o.deletions = null, o.memoizedProps = s.memoizedProps, o.memoizedState = s.memoizedState, o.updateQueue = s.updateQueue, o.type = s.type, e = s.dependencies, o.dependencies = e === null ? null : {
                lanes: e.lanes,
                firstContext: e.firstContext
              }), n = n.sibling;
              return Fe(Me, Me.current & 1 | 2), t.child;
            }
            e = e.sibling;
          }
          o.tail !== null && Ze() > gi && (t.flags |= 128, r = true, Fi(o, false), t.lanes = 4194304);
        }
        else {
          if (!r) if (e = Bs(s), e !== null) {
            if (t.flags |= 128, r = true, n = e.updateQueue, n !== null && (t.updateQueue = n, t.flags |= 4), Fi(o, true), o.tail === null && o.tailMode === "hidden" && !s.alternate && !Ue) return _t(t), null;
          } else 2 * Ze() - o.renderingStartTime > gi && n !== 1073741824 && (t.flags |= 128, r = true, Fi(o, false), t.lanes = 4194304);
          o.isBackwards ? (s.sibling = t.child, t.child = s) : (n = o.last, n !== null ? n.sibling = s : t.child = s, o.last = s);
        }
        return o.tail !== null ? (t = o.tail, o.rendering = t, o.tail = t.sibling, o.renderingStartTime = Ze(), t.sibling = null, n = Me.current, Fe(Me, r ? n & 1 | 2 : n & 1), t) : (_t(t), null);
      case 22:
      case 23:
        return ic(), r = t.memoizedState !== null, e !== null && e.memoizedState !== null !== r && (t.flags |= 8192), r && t.mode & 1 ? jt & 1073741824 && (_t(t), t.subtreeFlags & 6 && (t.flags |= 8192)) : _t(t), null;
      case 24:
        return null;
      case 25:
        return null;
    }
    throw Error(W(156, t.tag));
  }
  function Cy(e, t) {
    switch (Gu(t), t.tag) {
      case 1:
        return Bt(t.type) && Ps(), e = t.flags, e & 65536 ? (t.flags = e & -65537 | 128, t) : null;
      case 3:
        return hi(), Ge(Ut), Ge(xt), Ku(), e = t.flags, e & 65536 && !(e & 128) ? (t.flags = e & -65537 | 128, t) : null;
      case 5:
        return Vu(t), null;
      case 13:
        if (Ge(Me), e = t.memoizedState, e !== null && e.dehydrated !== null) {
          if (t.alternate === null) throw Error(W(340));
          di();
        }
        return e = t.flags, e & 65536 ? (t.flags = e & -65537 | 128, t) : null;
      case 19:
        return Ge(Me), null;
      case 4:
        return hi(), null;
      case 10:
        return $u(t.type._context), null;
      case 22:
      case 23:
        return ic(), null;
      case 24:
        return null;
      default:
        return null;
    }
  }
  var Zo = false, bt = false, Ty = typeof WeakSet == "function" ? WeakSet : Set, ee = null;
  function Jr(e, t) {
    var n = e.ref;
    if (n !== null) if (typeof n == "function") try {
      n(null);
    } catch (r) {
      Ye(e, t, r);
    }
    else n.current = null;
  }
  function Jl(e, t, n) {
    try {
      n();
    } catch (r) {
      Ye(e, t, r);
    }
  }
  var _d = false;
  function Ry(e, t) {
    if (zl = As, e = Ch(), zu(e)) {
      if ("selectionStart" in e) var n = {
        start: e.selectionStart,
        end: e.selectionEnd
      };
      else e: {
        n = (n = e.ownerDocument) && n.defaultView || window;
        var r = n.getSelection && n.getSelection();
        if (r && r.rangeCount !== 0) {
          n = r.anchorNode;
          var i = r.anchorOffset, o = r.focusNode;
          r = r.focusOffset;
          try {
            n.nodeType, o.nodeType;
          } catch {
            n = null;
            break e;
          }
          var s = 0, a = -1, l = -1, c = 0, h = 0, f = e, p = null;
          t: for (; ; ) {
            for (var y; f !== n || i !== 0 && f.nodeType !== 3 || (a = s + i), f !== o || r !== 0 && f.nodeType !== 3 || (l = s + r), f.nodeType === 3 && (s += f.nodeValue.length), (y = f.firstChild) !== null; ) p = f, f = y;
            for (; ; ) {
              if (f === e) break t;
              if (p === n && ++c === i && (a = s), p === o && ++h === r && (l = s), (y = f.nextSibling) !== null) break;
              f = p, p = f.parentNode;
            }
            f = y;
          }
          n = a === -1 || l === -1 ? null : {
            start: a,
            end: l
          };
        } else n = null;
      }
      n = n || {
        start: 0,
        end: 0
      };
    } else n = null;
    for (Ol = {
      focusedElem: e,
      selectionRange: n
    }, As = false, ee = t; ee !== null; ) if (t = ee, e = t.child, (t.subtreeFlags & 1028) !== 0 && e !== null) e.return = t, ee = e;
    else for (; ee !== null; ) {
      t = ee;
      try {
        var k = t.alternate;
        if (t.flags & 1024) switch (t.tag) {
          case 0:
          case 11:
          case 15:
            break;
          case 1:
            if (k !== null) {
              var b = k.memoizedProps, I = k.memoizedState, _ = t.stateNode, m = _.getSnapshotBeforeUpdate(t.elementType === t.type ? b : gn(t.type, b), I);
              _.__reactInternalSnapshotBeforeUpdate = m;
            }
            break;
          case 3:
            var v = t.stateNode.containerInfo;
            v.nodeType === 1 ? v.textContent = "" : v.nodeType === 9 && v.documentElement && v.removeChild(v.documentElement);
            break;
          case 5:
          case 6:
          case 4:
          case 17:
            break;
          default:
            throw Error(W(163));
        }
      } catch (E) {
        Ye(t, t.return, E);
      }
      if (e = t.sibling, e !== null) {
        e.return = t.return, ee = e;
        break;
      }
      ee = t.return;
    }
    return k = _d, _d = false, k;
  }
  function io(e, t, n) {
    var r = t.updateQueue;
    if (r = r !== null ? r.lastEffect : null, r !== null) {
      var i = r = r.next;
      do {
        if ((i.tag & e) === e) {
          var o = i.destroy;
          i.destroy = void 0, o !== void 0 && Jl(t, n, o);
        }
        i = i.next;
      } while (i !== r);
    }
  }
  function ca(e, t) {
    if (t = t.updateQueue, t = t !== null ? t.lastEffect : null, t !== null) {
      var n = t = t.next;
      do {
        if ((n.tag & e) === e) {
          var r = n.create;
          n.destroy = r();
        }
        n = n.next;
      } while (n !== t);
    }
  }
  function eu(e) {
    var t = e.ref;
    if (t !== null) {
      var n = e.stateNode;
      switch (e.tag) {
        case 5:
          e = n;
          break;
        default:
          e = n;
      }
      typeof t == "function" ? t(e) : t.current = e;
    }
  }
  function _p(e) {
    var t = e.alternate;
    t !== null && (e.alternate = null, _p(t)), e.child = null, e.deletions = null, e.sibling = null, e.tag === 5 && (t = e.stateNode, t !== null && (delete t[Tn], delete t[wo], delete t[Bl], delete t[cy], delete t[dy])), e.stateNode = null, e.return = null, e.dependencies = null, e.memoizedProps = null, e.memoizedState = null, e.pendingProps = null, e.stateNode = null, e.updateQueue = null;
  }
  function kp(e) {
    return e.tag === 5 || e.tag === 3 || e.tag === 4;
  }
  function kd(e) {
    e: for (; ; ) {
      for (; e.sibling === null; ) {
        if (e.return === null || kp(e.return)) return null;
        e = e.return;
      }
      for (e.sibling.return = e.return, e = e.sibling; e.tag !== 5 && e.tag !== 6 && e.tag !== 18; ) {
        if (e.flags & 2 || e.child === null || e.tag === 4) continue e;
        e.child.return = e, e = e.child;
      }
      if (!(e.flags & 2)) return e.stateNode;
    }
  }
  function tu(e, t, n) {
    var r = e.tag;
    if (r === 5 || r === 6) e = e.stateNode, t ? n.nodeType === 8 ? n.parentNode.insertBefore(e, t) : n.insertBefore(e, t) : (n.nodeType === 8 ? (t = n.parentNode, t.insertBefore(e, n)) : (t = n, t.appendChild(e)), n = n._reactRootContainer, n != null || t.onclick !== null || (t.onclick = Ds));
    else if (r !== 4 && (e = e.child, e !== null)) for (tu(e, t, n), e = e.sibling; e !== null; ) tu(e, t, n), e = e.sibling;
  }
  function nu(e, t, n) {
    var r = e.tag;
    if (r === 5 || r === 6) e = e.stateNode, t ? n.insertBefore(e, t) : n.appendChild(e);
    else if (r !== 4 && (e = e.child, e !== null)) for (nu(e, t, n), e = e.sibling; e !== null; ) nu(e, t, n), e = e.sibling;
  }
  var ft = null, mn = false;
  function qn(e, t, n) {
    for (n = n.child; n !== null; ) bp(e, t, n), n = n.sibling;
  }
  function bp(e, t, n) {
    if (An && typeof An.onCommitFiberUnmount == "function") try {
      An.onCommitFiberUnmount(na, n);
    } catch {
    }
    switch (n.tag) {
      case 5:
        bt || Jr(n, t);
      case 6:
        var r = ft, i = mn;
        ft = null, qn(e, t, n), ft = r, mn = i, ft !== null && (mn ? (e = ft, n = n.stateNode, e.nodeType === 8 ? e.parentNode.removeChild(n) : e.removeChild(n)) : ft.removeChild(n.stateNode));
        break;
      case 18:
        ft !== null && (mn ? (e = ft, n = n.stateNode, e.nodeType === 8 ? $a(e.parentNode, n) : e.nodeType === 1 && $a(e, n), po(e)) : $a(ft, n.stateNode));
        break;
      case 4:
        r = ft, i = mn, ft = n.stateNode.containerInfo, mn = true, qn(e, t, n), ft = r, mn = i;
        break;
      case 0:
      case 11:
      case 14:
      case 15:
        if (!bt && (r = n.updateQueue, r !== null && (r = r.lastEffect, r !== null))) {
          i = r = r.next;
          do {
            var o = i, s = o.destroy;
            o = o.tag, s !== void 0 && (o & 2 || o & 4) && Jl(n, t, s), i = i.next;
          } while (i !== r);
        }
        qn(e, t, n);
        break;
      case 1:
        if (!bt && (Jr(n, t), r = n.stateNode, typeof r.componentWillUnmount == "function")) try {
          r.props = n.memoizedProps, r.state = n.memoizedState, r.componentWillUnmount();
        } catch (a) {
          Ye(n, t, a);
        }
        qn(e, t, n);
        break;
      case 21:
        qn(e, t, n);
        break;
      case 22:
        n.mode & 1 ? (bt = (r = bt) || n.memoizedState !== null, qn(e, t, n), bt = r) : qn(e, t, n);
        break;
      default:
        qn(e, t, n);
    }
  }
  function bd(e) {
    var t = e.updateQueue;
    if (t !== null) {
      e.updateQueue = null;
      var n = e.stateNode;
      n === null && (n = e.stateNode = new Ty()), t.forEach(function(r) {
        var i = Oy.bind(null, e, r);
        n.has(r) || (n.add(r), r.then(i, i));
      });
    }
  }
  function dn(e, t) {
    var n = t.deletions;
    if (n !== null) for (var r = 0; r < n.length; r++) {
      var i = n[r];
      try {
        var o = e, s = t, a = s;
        e: for (; a !== null; ) {
          switch (a.tag) {
            case 5:
              ft = a.stateNode, mn = false;
              break e;
            case 3:
              ft = a.stateNode.containerInfo, mn = true;
              break e;
            case 4:
              ft = a.stateNode.containerInfo, mn = true;
              break e;
          }
          a = a.return;
        }
        if (ft === null) throw Error(W(160));
        bp(o, s, i), ft = null, mn = false;
        var l = i.alternate;
        l !== null && (l.return = null), i.return = null;
      } catch (c) {
        Ye(i, t, c);
      }
    }
    if (t.subtreeFlags & 12854) for (t = t.child; t !== null; ) xp(t, e), t = t.sibling;
  }
  function xp(e, t) {
    var n = e.alternate, r = e.flags;
    switch (e.tag) {
      case 0:
      case 11:
      case 14:
      case 15:
        if (dn(t, e), kn(e), r & 4) {
          try {
            io(3, e, e.return), ca(3, e);
          } catch (b) {
            Ye(e, e.return, b);
          }
          try {
            io(5, e, e.return);
          } catch (b) {
            Ye(e, e.return, b);
          }
        }
        break;
      case 1:
        dn(t, e), kn(e), r & 512 && n !== null && Jr(n, n.return);
        break;
      case 5:
        if (dn(t, e), kn(e), r & 512 && n !== null && Jr(n, n.return), e.flags & 32) {
          var i = e.stateNode;
          try {
            uo(i, "");
          } catch (b) {
            Ye(e, e.return, b);
          }
        }
        if (r & 4 && (i = e.stateNode, i != null)) {
          var o = e.memoizedProps, s = n !== null ? n.memoizedProps : o, a = e.type, l = e.updateQueue;
          if (e.updateQueue = null, l !== null) try {
            a === "input" && o.type === "radio" && o.name != null && Kf(i, o), Cl(a, s);
            var c = Cl(a, o);
            for (s = 0; s < l.length; s += 2) {
              var h = l[s], f = l[s + 1];
              h === "style" ? qf(i, f) : h === "dangerouslySetInnerHTML" ? Xf(i, f) : h === "children" ? uo(i, f) : ku(i, h, f, c);
            }
            switch (a) {
              case "input":
                Sl(i, o);
                break;
              case "textarea":
                Yf(i, o);
                break;
              case "select":
                var p = i._wrapperState.wasMultiple;
                i._wrapperState.wasMultiple = !!o.multiple;
                var y = o.value;
                y != null ? ti(i, !!o.multiple, y, false) : p !== !!o.multiple && (o.defaultValue != null ? ti(i, !!o.multiple, o.defaultValue, true) : ti(i, !!o.multiple, o.multiple ? [] : "", false));
            }
            i[wo] = o;
          } catch (b) {
            Ye(e, e.return, b);
          }
        }
        break;
      case 6:
        if (dn(t, e), kn(e), r & 4) {
          if (e.stateNode === null) throw Error(W(162));
          i = e.stateNode, o = e.memoizedProps;
          try {
            i.nodeValue = o;
          } catch (b) {
            Ye(e, e.return, b);
          }
        }
        break;
      case 3:
        if (dn(t, e), kn(e), r & 4 && n !== null && n.memoizedState.isDehydrated) try {
          po(t.containerInfo);
        } catch (b) {
          Ye(e, e.return, b);
        }
        break;
      case 4:
        dn(t, e), kn(e);
        break;
      case 13:
        dn(t, e), kn(e), i = e.child, i.flags & 8192 && (o = i.memoizedState !== null, i.stateNode.isHidden = o, !o || i.alternate !== null && i.alternate.memoizedState !== null || (nc = Ze())), r & 4 && bd(e);
        break;
      case 22:
        if (h = n !== null && n.memoizedState !== null, e.mode & 1 ? (bt = (c = bt) || h, dn(t, e), bt = c) : dn(t, e), kn(e), r & 8192) {
          if (c = e.memoizedState !== null, (e.stateNode.isHidden = c) && !h && e.mode & 1) for (ee = e, h = e.child; h !== null; ) {
            for (f = ee = h; ee !== null; ) {
              switch (p = ee, y = p.child, p.tag) {
                case 0:
                case 11:
                case 14:
                case 15:
                  io(4, p, p.return);
                  break;
                case 1:
                  Jr(p, p.return);
                  var k = p.stateNode;
                  if (typeof k.componentWillUnmount == "function") {
                    r = p, n = p.return;
                    try {
                      t = r, k.props = t.memoizedProps, k.state = t.memoizedState, k.componentWillUnmount();
                    } catch (b) {
                      Ye(r, n, b);
                    }
                  }
                  break;
                case 5:
                  Jr(p, p.return);
                  break;
                case 22:
                  if (p.memoizedState !== null) {
                    Cd(f);
                    continue;
                  }
              }
              y !== null ? (y.return = p, ee = y) : Cd(f);
            }
            h = h.sibling;
          }
          e: for (h = null, f = e; ; ) {
            if (f.tag === 5) {
              if (h === null) {
                h = f;
                try {
                  i = f.stateNode, c ? (o = i.style, typeof o.setProperty == "function" ? o.setProperty("display", "none", "important") : o.display = "none") : (a = f.stateNode, l = f.memoizedProps.style, s = l != null && l.hasOwnProperty("display") ? l.display : null, a.style.display = Zf("display", s));
                } catch (b) {
                  Ye(e, e.return, b);
                }
              }
            } else if (f.tag === 6) {
              if (h === null) try {
                f.stateNode.nodeValue = c ? "" : f.memoizedProps;
              } catch (b) {
                Ye(e, e.return, b);
              }
            } else if ((f.tag !== 22 && f.tag !== 23 || f.memoizedState === null || f === e) && f.child !== null) {
              f.child.return = f, f = f.child;
              continue;
            }
            if (f === e) break e;
            for (; f.sibling === null; ) {
              if (f.return === null || f.return === e) break e;
              h === f && (h = null), f = f.return;
            }
            h === f && (h = null), f.sibling.return = f.return, f = f.sibling;
          }
        }
        break;
      case 19:
        dn(t, e), kn(e), r & 4 && bd(e);
        break;
      case 21:
        break;
      default:
        dn(t, e), kn(e);
    }
  }
  function kn(e) {
    var t = e.flags;
    if (t & 2) {
      try {
        e: {
          for (var n = e.return; n !== null; ) {
            if (kp(n)) {
              var r = n;
              break e;
            }
            n = n.return;
          }
          throw Error(W(160));
        }
        switch (r.tag) {
          case 5:
            var i = r.stateNode;
            r.flags & 32 && (uo(i, ""), r.flags &= -33);
            var o = kd(e);
            nu(e, o, i);
            break;
          case 3:
          case 4:
            var s = r.stateNode.containerInfo, a = kd(e);
            tu(e, a, s);
            break;
          default:
            throw Error(W(161));
        }
      } catch (l) {
        Ye(e, e.return, l);
      }
      e.flags &= -3;
    }
    t & 4096 && (e.flags &= -4097);
  }
  function Ay(e, t, n) {
    ee = e, Cp(e);
  }
  function Cp(e, t, n) {
    for (var r = (e.mode & 1) !== 0; ee !== null; ) {
      var i = ee, o = i.child;
      if (i.tag === 22 && r) {
        var s = i.memoizedState !== null || Zo;
        if (!s) {
          var a = i.alternate, l = a !== null && a.memoizedState !== null || bt;
          a = Zo;
          var c = bt;
          if (Zo = s, (bt = l) && !c) for (ee = i; ee !== null; ) s = ee, l = s.child, s.tag === 22 && s.memoizedState !== null ? Td(i) : l !== null ? (l.return = s, ee = l) : Td(i);
          for (; o !== null; ) ee = o, Cp(o), o = o.sibling;
          ee = i, Zo = a, bt = c;
        }
        xd(e);
      } else i.subtreeFlags & 8772 && o !== null ? (o.return = i, ee = o) : xd(e);
    }
  }
  function xd(e) {
    for (; ee !== null; ) {
      var t = ee;
      if (t.flags & 8772) {
        var n = t.alternate;
        try {
          if (t.flags & 8772) switch (t.tag) {
            case 0:
            case 11:
            case 15:
              bt || ca(5, t);
              break;
            case 1:
              var r = t.stateNode;
              if (t.flags & 4 && !bt) if (n === null) r.componentDidMount();
              else {
                var i = t.elementType === t.type ? n.memoizedProps : gn(t.type, n.memoizedProps);
                r.componentDidUpdate(i, n.memoizedState, r.__reactInternalSnapshotBeforeUpdate);
              }
              var o = t.updateQueue;
              o !== null && ud(t, o, r);
              break;
            case 3:
              var s = t.updateQueue;
              if (s !== null) {
                if (n = null, t.child !== null) switch (t.child.tag) {
                  case 5:
                    n = t.child.stateNode;
                    break;
                  case 1:
                    n = t.child.stateNode;
                }
                ud(t, s, n);
              }
              break;
            case 5:
              var a = t.stateNode;
              if (n === null && t.flags & 4) {
                n = a;
                var l = t.memoizedProps;
                switch (t.type) {
                  case "button":
                  case "input":
                  case "select":
                  case "textarea":
                    l.autoFocus && n.focus();
                    break;
                  case "img":
                    l.src && (n.src = l.src);
                }
              }
              break;
            case 6:
              break;
            case 4:
              break;
            case 12:
              break;
            case 13:
              if (t.memoizedState === null) {
                var c = t.alternate;
                if (c !== null) {
                  var h = c.memoizedState;
                  if (h !== null) {
                    var f = h.dehydrated;
                    f !== null && po(f);
                  }
                }
              }
              break;
            case 19:
            case 17:
            case 21:
            case 22:
            case 23:
            case 25:
              break;
            default:
              throw Error(W(163));
          }
          bt || t.flags & 512 && eu(t);
        } catch (p) {
          Ye(t, t.return, p);
        }
      }
      if (t === e) {
        ee = null;
        break;
      }
      if (n = t.sibling, n !== null) {
        n.return = t.return, ee = n;
        break;
      }
      ee = t.return;
    }
  }
  function Cd(e) {
    for (; ee !== null; ) {
      var t = ee;
      if (t === e) {
        ee = null;
        break;
      }
      var n = t.sibling;
      if (n !== null) {
        n.return = t.return, ee = n;
        break;
      }
      ee = t.return;
    }
  }
  function Td(e) {
    for (; ee !== null; ) {
      var t = ee;
      try {
        switch (t.tag) {
          case 0:
          case 11:
          case 15:
            var n = t.return;
            try {
              ca(4, t);
            } catch (l) {
              Ye(t, n, l);
            }
            break;
          case 1:
            var r = t.stateNode;
            if (typeof r.componentDidMount == "function") {
              var i = t.return;
              try {
                r.componentDidMount();
              } catch (l) {
                Ye(t, i, l);
              }
            }
            var o = t.return;
            try {
              eu(t);
            } catch (l) {
              Ye(t, o, l);
            }
            break;
          case 5:
            var s = t.return;
            try {
              eu(t);
            } catch (l) {
              Ye(t, s, l);
            }
        }
      } catch (l) {
        Ye(t, t.return, l);
      }
      if (t === e) {
        ee = null;
        break;
      }
      var a = t.sibling;
      if (a !== null) {
        a.return = t.return, ee = a;
        break;
      }
      ee = t.return;
    }
  }
  var Ly = Math.ceil, js = Yn.ReactCurrentDispatcher, ec = Yn.ReactCurrentOwner, tn = Yn.ReactCurrentBatchConfig, be = 0, dt = null, Je = null, pt = 0, jt = 0, ei = wr(0), ot = 0, xo = null, Fr = 0, da = 0, tc = 0, oo = null, Ot = null, nc = 0, gi = 1 / 0, On = null, Hs = false, ru = null, hr = null, qo = false, ar = null, Ws = 0, so = 0, iu = null, ys = -1, ws = 0;
  function Lt() {
    return be & 6 ? Ze() : ys !== -1 ? ys : ys = Ze();
  }
  function pr(e) {
    return e.mode & 1 ? be & 2 && pt !== 0 ? pt & -pt : hy.transition !== null ? (ws === 0 && (ws = ch()), ws) : (e = De, e !== 0 || (e = window.event, e = e === void 0 ? 16 : vh(e.type)), e) : 1;
  }
  function En(e, t, n, r) {
    if (50 < so) throw so = 0, iu = null, Error(W(185));
    Ao(e, n, r), (!(be & 2) || e !== dt) && (e === dt && (!(be & 2) && (da |= n), ot === 4 && or(e, pt)), Mt(e, r), n === 1 && be === 0 && !(t.mode & 1) && (gi = Ze() + 500, aa && Er()));
  }
  function Mt(e, t) {
    var n = e.callbackNode;
    hv(e, t);
    var r = Rs(e, e === dt ? pt : 0);
    if (r === 0) n !== null && zc(n), e.callbackNode = null, e.callbackPriority = 0;
    else if (t = r & -r, e.callbackPriority !== t) {
      if (n != null && zc(n), t === 1) e.tag === 0 ? fy(Rd.bind(null, e)) : zh(Rd.bind(null, e)), ly(function() {
        !(be & 6) && Er();
      }), n = null;
      else {
        switch (dh(r)) {
          case 1:
            n = Ru;
            break;
          case 4:
            n = lh;
            break;
          case 16:
            n = Ts;
            break;
          case 536870912:
            n = uh;
            break;
          default:
            n = Ts;
        }
        n = Np(n, Tp.bind(null, e));
      }
      e.callbackPriority = t, e.callbackNode = n;
    }
  }
  function Tp(e, t) {
    if (ys = -1, ws = 0, be & 6) throw Error(W(327));
    var n = e.callbackNode;
    if (si() && e.callbackNode !== n) return null;
    var r = Rs(e, e === dt ? pt : 0);
    if (r === 0) return null;
    if (r & 30 || r & e.expiredLanes || t) t = Vs(e, r);
    else {
      t = r;
      var i = be;
      be |= 2;
      var o = Ap();
      (dt !== e || pt !== t) && (On = null, gi = Ze() + 500, Lr(e, t));
      do
        try {
          Py();
          break;
        } catch (a) {
          Rp(e, a);
        }
      while (true);
      Mu(), js.current = o, be = i, Je !== null ? t = 0 : (dt = null, pt = 0, t = ot);
    }
    if (t !== 0) {
      if (t === 2 && (i = Il(e), i !== 0 && (r = i, t = ou(e, i))), t === 1) throw n = xo, Lr(e, 0), or(e, r), Mt(e, Ze()), n;
      if (t === 6) or(e, r);
      else {
        if (i = e.current.alternate, !(r & 30) && !Iy(i) && (t = Vs(e, r), t === 2 && (o = Il(e), o !== 0 && (r = o, t = ou(e, o))), t === 1)) throw n = xo, Lr(e, 0), or(e, r), Mt(e, Ze()), n;
        switch (e.finishedWork = i, e.finishedLanes = r, t) {
          case 0:
          case 1:
            throw Error(W(345));
          case 2:
            xr(e, Ot, On);
            break;
          case 3:
            if (or(e, r), (r & 130023424) === r && (t = nc + 500 - Ze(), 10 < t)) {
              if (Rs(e, 0) !== 0) break;
              if (i = e.suspendedLanes, (i & r) !== r) {
                Lt(), e.pingedLanes |= e.suspendedLanes & i;
                break;
              }
              e.timeoutHandle = Ul(xr.bind(null, e, Ot, On), t);
              break;
            }
            xr(e, Ot, On);
            break;
          case 4:
            if (or(e, r), (r & 4194240) === r) break;
            for (t = e.eventTimes, i = -1; 0 < r; ) {
              var s = 31 - wn(r);
              o = 1 << s, s = t[s], s > i && (i = s), r &= ~o;
            }
            if (r = i, r = Ze() - r, r = (120 > r ? 120 : 480 > r ? 480 : 1080 > r ? 1080 : 1920 > r ? 1920 : 3e3 > r ? 3e3 : 4320 > r ? 4320 : 1960 * Ly(r / 1960)) - r, 10 < r) {
              e.timeoutHandle = Ul(xr.bind(null, e, Ot, On), r);
              break;
            }
            xr(e, Ot, On);
            break;
          case 5:
            xr(e, Ot, On);
            break;
          default:
            throw Error(W(329));
        }
      }
    }
    return Mt(e, Ze()), e.callbackNode === n ? Tp.bind(null, e) : null;
  }
  function ou(e, t) {
    var n = oo;
    return e.current.memoizedState.isDehydrated && (Lr(e, t).flags |= 256), e = Vs(e, t), e !== 2 && (t = Ot, Ot = n, t !== null && su(t)), e;
  }
  function su(e) {
    Ot === null ? Ot = e : Ot.push.apply(Ot, e);
  }
  function Iy(e) {
    for (var t = e; ; ) {
      if (t.flags & 16384) {
        var n = t.updateQueue;
        if (n !== null && (n = n.stores, n !== null)) for (var r = 0; r < n.length; r++) {
          var i = n[r], o = i.getSnapshot;
          i = i.value;
          try {
            if (!Sn(o(), i)) return false;
          } catch {
            return false;
          }
        }
      }
      if (n = t.child, t.subtreeFlags & 16384 && n !== null) n.return = t, t = n;
      else {
        if (t === e) break;
        for (; t.sibling === null; ) {
          if (t.return === null || t.return === e) return true;
          t = t.return;
        }
        t.sibling.return = t.return, t = t.sibling;
      }
    }
    return true;
  }
  function or(e, t) {
    for (t &= ~tc, t &= ~da, e.suspendedLanes |= t, e.pingedLanes &= ~t, e = e.expirationTimes; 0 < t; ) {
      var n = 31 - wn(t), r = 1 << n;
      e[n] = -1, t &= ~r;
    }
  }
  function Rd(e) {
    if (be & 6) throw Error(W(327));
    si();
    var t = Rs(e, 0);
    if (!(t & 1)) return Mt(e, Ze()), null;
    var n = Vs(e, t);
    if (e.tag !== 0 && n === 2) {
      var r = Il(e);
      r !== 0 && (t = r, n = ou(e, r));
    }
    if (n === 1) throw n = xo, Lr(e, 0), or(e, t), Mt(e, Ze()), n;
    if (n === 6) throw Error(W(345));
    return e.finishedWork = e.current.alternate, e.finishedLanes = t, xr(e, Ot, On), Mt(e, Ze()), null;
  }
  function rc(e, t) {
    var n = be;
    be |= 1;
    try {
      return e(t);
    } finally {
      be = n, be === 0 && (gi = Ze() + 500, aa && Er());
    }
  }
  function zr(e) {
    ar !== null && ar.tag === 0 && !(be & 6) && si();
    var t = be;
    be |= 1;
    var n = tn.transition, r = De;
    try {
      if (tn.transition = null, De = 1, e) return e();
    } finally {
      De = r, tn.transition = n, be = t, !(be & 6) && Er();
    }
  }
  function ic() {
    jt = ei.current, Ge(ei);
  }
  function Lr(e, t) {
    e.finishedWork = null, e.finishedLanes = 0;
    var n = e.timeoutHandle;
    if (n !== -1 && (e.timeoutHandle = -1, ay(n)), Je !== null) for (n = Je.return; n !== null; ) {
      var r = n;
      switch (Gu(r), r.tag) {
        case 1:
          r = r.type.childContextTypes, r != null && Ps();
          break;
        case 3:
          hi(), Ge(Ut), Ge(xt), Ku();
          break;
        case 5:
          Vu(r);
          break;
        case 4:
          hi();
          break;
        case 13:
          Ge(Me);
          break;
        case 19:
          Ge(Me);
          break;
        case 10:
          $u(r.type._context);
          break;
        case 22:
        case 23:
          ic();
      }
      n = n.return;
    }
    if (dt = e, Je = e = gr(e.current, null), pt = jt = t, ot = 0, xo = null, tc = da = Fr = 0, Ot = oo = null, Rr !== null) {
      for (t = 0; t < Rr.length; t++) if (n = Rr[t], r = n.interleaved, r !== null) {
        n.interleaved = null;
        var i = r.next, o = n.pending;
        if (o !== null) {
          var s = o.next;
          o.next = i, r.next = s;
        }
        n.pending = r;
      }
      Rr = null;
    }
    return e;
  }
  function Rp(e, t) {
    do {
      var n = Je;
      try {
        if (Mu(), gs.current = $s, Ms) {
          for (var r = $e.memoizedState; r !== null; ) {
            var i = r.queue;
            i !== null && (i.pending = null), r = r.next;
          }
          Ms = false;
        }
        if (Nr = 0, ct = rt = $e = null, ro = false, _o = 0, ec.current = null, n === null || n.return === null) {
          ot = 1, xo = t, Je = null;
          break;
        }
        e: {
          var o = e, s = n.return, a = n, l = t;
          if (t = pt, a.flags |= 32768, l !== null && typeof l == "object" && typeof l.then == "function") {
            var c = l, h = a, f = h.tag;
            if (!(h.mode & 1) && (f === 0 || f === 11 || f === 15)) {
              var p = h.alternate;
              p ? (h.updateQueue = p.updateQueue, h.memoizedState = p.memoizedState, h.lanes = p.lanes) : (h.updateQueue = null, h.memoizedState = null);
            }
            var y = gd(s);
            if (y !== null) {
              y.flags &= -257, md(y, s, a, o, t), y.mode & 1 && pd(o, c, t), t = y, l = c;
              var k = t.updateQueue;
              if (k === null) {
                var b = /* @__PURE__ */ new Set();
                b.add(l), t.updateQueue = b;
              } else k.add(l);
              break e;
            } else {
              if (!(t & 1)) {
                pd(o, c, t), oc();
                break e;
              }
              l = Error(W(426));
            }
          } else if (Ue && a.mode & 1) {
            var I = gd(s);
            if (I !== null) {
              !(I.flags & 65536) && (I.flags |= 256), md(I, s, a, o, t), Uu(pi(l, a));
              break e;
            }
          }
          o = l = pi(l, a), ot !== 4 && (ot = 2), oo === null ? oo = [
            o
          ] : oo.push(o), o = s;
          do {
            switch (o.tag) {
              case 3:
                o.flags |= 65536, t &= -t, o.lanes |= t;
                var _ = dp(o, l, t);
                ld(o, _);
                break e;
              case 1:
                a = l;
                var m = o.type, v = o.stateNode;
                if (!(o.flags & 128) && (typeof m.getDerivedStateFromError == "function" || v !== null && typeof v.componentDidCatch == "function" && (hr === null || !hr.has(v)))) {
                  o.flags |= 65536, t &= -t, o.lanes |= t;
                  var E = fp(o, a, t);
                  ld(o, E);
                  break e;
                }
            }
            o = o.return;
          } while (o !== null);
        }
        Ip(n);
      } catch (A) {
        t = A, Je === n && n !== null && (Je = n = n.return);
        continue;
      }
      break;
    } while (true);
  }
  function Ap() {
    var e = js.current;
    return js.current = $s, e === null ? $s : e;
  }
  function oc() {
    (ot === 0 || ot === 3 || ot === 2) && (ot = 4), dt === null || !(Fr & 268435455) && !(da & 268435455) || or(dt, pt);
  }
  function Vs(e, t) {
    var n = be;
    be |= 2;
    var r = Ap();
    (dt !== e || pt !== t) && (On = null, Lr(e, t));
    do
      try {
        Dy();
        break;
      } catch (i) {
        Rp(e, i);
      }
    while (true);
    if (Mu(), be = n, js.current = r, Je !== null) throw Error(W(261));
    return dt = null, pt = 0, ot;
  }
  function Dy() {
    for (; Je !== null; ) Lp(Je);
  }
  function Py() {
    for (; Je !== null && !iv(); ) Lp(Je);
  }
  function Lp(e) {
    var t = Pp(e.alternate, e, jt);
    e.memoizedProps = e.pendingProps, t === null ? Ip(e) : Je = t, ec.current = null;
  }
  function Ip(e) {
    var t = e;
    do {
      var n = t.alternate;
      if (e = t.return, t.flags & 32768) {
        if (n = Cy(n, t), n !== null) {
          n.flags &= 32767, Je = n;
          return;
        }
        if (e !== null) e.flags |= 32768, e.subtreeFlags = 0, e.deletions = null;
        else {
          ot = 6, Je = null;
          return;
        }
      } else if (n = xy(n, t, jt), n !== null) {
        Je = n;
        return;
      }
      if (t = t.sibling, t !== null) {
        Je = t;
        return;
      }
      Je = t = e;
    } while (t !== null);
    ot === 0 && (ot = 5);
  }
  function xr(e, t, n) {
    var r = De, i = tn.transition;
    try {
      tn.transition = null, De = 1, Ny(e, t, n, r);
    } finally {
      tn.transition = i, De = r;
    }
    return null;
  }
  function Ny(e, t, n, r) {
    do
      si();
    while (ar !== null);
    if (be & 6) throw Error(W(327));
    n = e.finishedWork;
    var i = e.finishedLanes;
    if (n === null) return null;
    if (e.finishedWork = null, e.finishedLanes = 0, n === e.current) throw Error(W(177));
    e.callbackNode = null, e.callbackPriority = 0;
    var o = n.lanes | n.childLanes;
    if (pv(e, o), e === dt && (Je = dt = null, pt = 0), !(n.subtreeFlags & 2064) && !(n.flags & 2064) || qo || (qo = true, Np(Ts, function() {
      return si(), null;
    })), o = (n.flags & 15990) !== 0, n.subtreeFlags & 15990 || o) {
      o = tn.transition, tn.transition = null;
      var s = De;
      De = 1;
      var a = be;
      be |= 4, ec.current = null, Ry(e, n), xp(n, e), ey(Ol), As = !!zl, Ol = zl = null, e.current = n, Ay(n), ov(), be = a, De = s, tn.transition = o;
    } else e.current = n;
    if (qo && (qo = false, ar = e, Ws = i), o = e.pendingLanes, o === 0 && (hr = null), lv(n.stateNode), Mt(e, Ze()), t !== null) for (r = e.onRecoverableError, n = 0; n < t.length; n++) i = t[n], r(i.value, {
      componentStack: i.stack,
      digest: i.digest
    });
    if (Hs) throw Hs = false, e = ru, ru = null, e;
    return Ws & 1 && e.tag !== 0 && si(), o = e.pendingLanes, o & 1 ? e === iu ? so++ : (so = 0, iu = e) : so = 0, Er(), null;
  }
  function si() {
    if (ar !== null) {
      var e = dh(Ws), t = tn.transition, n = De;
      try {
        if (tn.transition = null, De = 16 > e ? 16 : e, ar === null) var r = false;
        else {
          if (e = ar, ar = null, Ws = 0, be & 6) throw Error(W(331));
          var i = be;
          for (be |= 4, ee = e.current; ee !== null; ) {
            var o = ee, s = o.child;
            if (ee.flags & 16) {
              var a = o.deletions;
              if (a !== null) {
                for (var l = 0; l < a.length; l++) {
                  var c = a[l];
                  for (ee = c; ee !== null; ) {
                    var h = ee;
                    switch (h.tag) {
                      case 0:
                      case 11:
                      case 15:
                        io(8, h, o);
                    }
                    var f = h.child;
                    if (f !== null) f.return = h, ee = f;
                    else for (; ee !== null; ) {
                      h = ee;
                      var p = h.sibling, y = h.return;
                      if (_p(h), h === c) {
                        ee = null;
                        break;
                      }
                      if (p !== null) {
                        p.return = y, ee = p;
                        break;
                      }
                      ee = y;
                    }
                  }
                }
                var k = o.alternate;
                if (k !== null) {
                  var b = k.child;
                  if (b !== null) {
                    k.child = null;
                    do {
                      var I = b.sibling;
                      b.sibling = null, b = I;
                    } while (b !== null);
                  }
                }
                ee = o;
              }
            }
            if (o.subtreeFlags & 2064 && s !== null) s.return = o, ee = s;
            else e: for (; ee !== null; ) {
              if (o = ee, o.flags & 2048) switch (o.tag) {
                case 0:
                case 11:
                case 15:
                  io(9, o, o.return);
              }
              var _ = o.sibling;
              if (_ !== null) {
                _.return = o.return, ee = _;
                break e;
              }
              ee = o.return;
            }
          }
          var m = e.current;
          for (ee = m; ee !== null; ) {
            s = ee;
            var v = s.child;
            if (s.subtreeFlags & 2064 && v !== null) v.return = s, ee = v;
            else e: for (s = m; ee !== null; ) {
              if (a = ee, a.flags & 2048) try {
                switch (a.tag) {
                  case 0:
                  case 11:
                  case 15:
                    ca(9, a);
                }
              } catch (A) {
                Ye(a, a.return, A);
              }
              if (a === s) {
                ee = null;
                break e;
              }
              var E = a.sibling;
              if (E !== null) {
                E.return = a.return, ee = E;
                break e;
              }
              ee = a.return;
            }
          }
          if (be = i, Er(), An && typeof An.onPostCommitFiberRoot == "function") try {
            An.onPostCommitFiberRoot(na, e);
          } catch {
          }
          r = true;
        }
        return r;
      } finally {
        De = n, tn.transition = t;
      }
    }
    return false;
  }
  function Ad(e, t, n) {
    t = pi(n, t), t = dp(e, t, 1), e = fr(e, t, 1), t = Lt(), e !== null && (Ao(e, 1, t), Mt(e, t));
  }
  function Ye(e, t, n) {
    if (e.tag === 3) Ad(e, e, n);
    else for (; t !== null; ) {
      if (t.tag === 3) {
        Ad(t, e, n);
        break;
      } else if (t.tag === 1) {
        var r = t.stateNode;
        if (typeof t.type.getDerivedStateFromError == "function" || typeof r.componentDidCatch == "function" && (hr === null || !hr.has(r))) {
          e = pi(n, e), e = fp(t, e, 1), t = fr(t, e, 1), e = Lt(), t !== null && (Ao(t, 1, e), Mt(t, e));
          break;
        }
      }
      t = t.return;
    }
  }
  function Fy(e, t, n) {
    var r = e.pingCache;
    r !== null && r.delete(t), t = Lt(), e.pingedLanes |= e.suspendedLanes & n, dt === e && (pt & n) === n && (ot === 4 || ot === 3 && (pt & 130023424) === pt && 500 > Ze() - nc ? Lr(e, 0) : tc |= n), Mt(e, t);
  }
  function Dp(e, t) {
    t === 0 && (e.mode & 1 ? (t = $o, $o <<= 1, !($o & 130023424) && ($o = 4194304)) : t = 1);
    var n = Lt();
    e = Vn(e, t), e !== null && (Ao(e, t, n), Mt(e, n));
  }
  function zy(e) {
    var t = e.memoizedState, n = 0;
    t !== null && (n = t.retryLane), Dp(e, n);
  }
  function Oy(e, t) {
    var n = 0;
    switch (e.tag) {
      case 13:
        var r = e.stateNode, i = e.memoizedState;
        i !== null && (n = i.retryLane);
        break;
      case 19:
        r = e.stateNode;
        break;
      default:
        throw Error(W(314));
    }
    r !== null && r.delete(t), Dp(e, n);
  }
  var Pp;
  Pp = function(e, t, n) {
    if (e !== null) if (e.memoizedProps !== t.pendingProps || Ut.current) Gt = true;
    else {
      if (!(e.lanes & n) && !(t.flags & 128)) return Gt = false, by(e, t, n);
      Gt = !!(e.flags & 131072);
    }
    else Gt = false, Ue && t.flags & 1048576 && Oh(t, zs, t.index);
    switch (t.lanes = 0, t.tag) {
      case 2:
        var r = t.type;
        vs(e, t), e = t.pendingProps;
        var i = ci(t, xt.current);
        oi(t, n), i = Qu(null, t, r, e, i, n);
        var o = Xu();
        return t.flags |= 1, typeof i == "object" && i !== null && typeof i.render == "function" && i.$$typeof === void 0 ? (t.tag = 1, t.memoizedState = null, t.updateQueue = null, Bt(r) ? (o = true, Ns(t)) : o = false, t.memoizedState = i.state !== null && i.state !== void 0 ? i.state : null, Hu(t), i.updater = ua, t.stateNode = i, i._reactInternals = t, Vl(t, r, e, n), t = Ql(null, t, r, true, o, n)) : (t.tag = 0, Ue && o && Ou(t), At(null, t, i, n), t = t.child), t;
      case 16:
        r = t.elementType;
        e: {
          switch (vs(e, t), e = t.pendingProps, i = r._init, r = i(r._payload), t.type = r, i = t.tag = Uy(r), e = gn(r, e), i) {
            case 0:
              t = Yl(null, t, r, e, n);
              break e;
            case 1:
              t = wd(null, t, r, e, n);
              break e;
            case 11:
              t = vd(null, t, r, e, n);
              break e;
            case 14:
              t = yd(null, t, r, gn(r.type, e), n);
              break e;
          }
          throw Error(W(306, r, ""));
        }
        return t;
      case 0:
        return r = t.type, i = t.pendingProps, i = t.elementType === r ? i : gn(r, i), Yl(e, t, r, i, n);
      case 1:
        return r = t.type, i = t.pendingProps, i = t.elementType === r ? i : gn(r, i), wd(e, t, r, i, n);
      case 3:
        e: {
          if (mp(t), e === null) throw Error(W(387));
          r = t.pendingProps, o = t.memoizedState, i = o.element, jh(e, t), Us(t, r, null, n);
          var s = t.memoizedState;
          if (r = s.element, o.isDehydrated) if (o = {
            element: r,
            isDehydrated: false,
            cache: s.cache,
            pendingSuspenseBoundaries: s.pendingSuspenseBoundaries,
            transitions: s.transitions
          }, t.updateQueue.baseState = o, t.memoizedState = o, t.flags & 256) {
            i = pi(Error(W(423)), t), t = Ed(e, t, r, n, i);
            break e;
          } else if (r !== i) {
            i = pi(Error(W(424)), t), t = Ed(e, t, r, n, i);
            break e;
          } else for (Ht = dr(t.stateNode.containerInfo.firstChild), Wt = t, Ue = true, vn = null, n = Mh(t, null, r, n), t.child = n; n; ) n.flags = n.flags & -3 | 4096, n = n.sibling;
          else {
            if (di(), r === i) {
              t = Kn(e, t, n);
              break e;
            }
            At(e, t, r, n);
          }
          t = t.child;
        }
        return t;
      case 5:
        return Hh(t), e === null && jl(t), r = t.type, i = t.pendingProps, o = e !== null ? e.memoizedProps : null, s = i.children, Gl(r, i) ? s = null : o !== null && Gl(r, o) && (t.flags |= 32), gp(e, t), At(e, t, s, n), t.child;
      case 6:
        return e === null && jl(t), null;
      case 13:
        return vp(e, t, n);
      case 4:
        return Wu(t, t.stateNode.containerInfo), r = t.pendingProps, e === null ? t.child = fi(t, null, r, n) : At(e, t, r, n), t.child;
      case 11:
        return r = t.type, i = t.pendingProps, i = t.elementType === r ? i : gn(r, i), vd(e, t, r, i, n);
      case 7:
        return At(e, t, t.pendingProps, n), t.child;
      case 8:
        return At(e, t, t.pendingProps.children, n), t.child;
      case 12:
        return At(e, t, t.pendingProps.children, n), t.child;
      case 10:
        e: {
          if (r = t.type._context, i = t.pendingProps, o = t.memoizedProps, s = i.value, Fe(Os, r._currentValue), r._currentValue = s, o !== null) if (Sn(o.value, s)) {
            if (o.children === i.children && !Ut.current) {
              t = Kn(e, t, n);
              break e;
            }
          } else for (o = t.child, o !== null && (o.return = t); o !== null; ) {
            var a = o.dependencies;
            if (a !== null) {
              s = o.child;
              for (var l = a.firstContext; l !== null; ) {
                if (l.context === r) {
                  if (o.tag === 1) {
                    l = $n(-1, n & -n), l.tag = 2;
                    var c = o.updateQueue;
                    if (c !== null) {
                      c = c.shared;
                      var h = c.pending;
                      h === null ? l.next = l : (l.next = h.next, h.next = l), c.pending = l;
                    }
                  }
                  o.lanes |= n, l = o.alternate, l !== null && (l.lanes |= n), Hl(o.return, n, t), a.lanes |= n;
                  break;
                }
                l = l.next;
              }
            } else if (o.tag === 10) s = o.type === t.type ? null : o.child;
            else if (o.tag === 18) {
              if (s = o.return, s === null) throw Error(W(341));
              s.lanes |= n, a = s.alternate, a !== null && (a.lanes |= n), Hl(s, n, t), s = o.sibling;
            } else s = o.child;
            if (s !== null) s.return = o;
            else for (s = o; s !== null; ) {
              if (s === t) {
                s = null;
                break;
              }
              if (o = s.sibling, o !== null) {
                o.return = s.return, s = o;
                break;
              }
              s = s.return;
            }
            o = s;
          }
          At(e, t, i.children, n), t = t.child;
        }
        return t;
      case 9:
        return i = t.type, r = t.pendingProps.children, oi(t, n), i = rn(i), r = r(i), t.flags |= 1, At(e, t, r, n), t.child;
      case 14:
        return r = t.type, i = gn(r, t.pendingProps), i = gn(r.type, i), yd(e, t, r, i, n);
      case 15:
        return hp(e, t, t.type, t.pendingProps, n);
      case 17:
        return r = t.type, i = t.pendingProps, i = t.elementType === r ? i : gn(r, i), vs(e, t), t.tag = 1, Bt(r) ? (e = true, Ns(t)) : e = false, oi(t, n), cp(t, r, i), Vl(t, r, i, n), Ql(null, t, r, true, e, n);
      case 19:
        return yp(e, t, n);
      case 22:
        return pp(e, t, n);
    }
    throw Error(W(156, t.tag));
  };
  function Np(e, t) {
    return ah(e, t);
  }
  function Gy(e, t, n, r) {
    this.tag = e, this.key = n, this.sibling = this.child = this.return = this.stateNode = this.type = this.elementType = null, this.index = 0, this.ref = null, this.pendingProps = t, this.dependencies = this.memoizedState = this.updateQueue = this.memoizedProps = null, this.mode = r, this.subtreeFlags = this.flags = 0, this.deletions = null, this.childLanes = this.lanes = 0, this.alternate = null;
  }
  function en(e, t, n, r) {
    return new Gy(e, t, n, r);
  }
  function sc(e) {
    return e = e.prototype, !(!e || !e.isReactComponent);
  }
  function Uy(e) {
    if (typeof e == "function") return sc(e) ? 1 : 0;
    if (e != null) {
      if (e = e.$$typeof, e === xu) return 11;
      if (e === Cu) return 14;
    }
    return 2;
  }
  function gr(e, t) {
    var n = e.alternate;
    return n === null ? (n = en(e.tag, t, e.key, e.mode), n.elementType = e.elementType, n.type = e.type, n.stateNode = e.stateNode, n.alternate = e, e.alternate = n) : (n.pendingProps = t, n.type = e.type, n.flags = 0, n.subtreeFlags = 0, n.deletions = null), n.flags = e.flags & 14680064, n.childLanes = e.childLanes, n.lanes = e.lanes, n.child = e.child, n.memoizedProps = e.memoizedProps, n.memoizedState = e.memoizedState, n.updateQueue = e.updateQueue, t = e.dependencies, n.dependencies = t === null ? null : {
      lanes: t.lanes,
      firstContext: t.firstContext
    }, n.sibling = e.sibling, n.index = e.index, n.ref = e.ref, n;
  }
  function Es(e, t, n, r, i, o) {
    var s = 2;
    if (r = e, typeof e == "function") sc(e) && (s = 1);
    else if (typeof e == "string") s = 5;
    else e: switch (e) {
      case Hr:
        return Ir(n.children, i, o, t);
      case bu:
        s = 8, i |= 8;
        break;
      case ml:
        return e = en(12, n, t, i | 2), e.elementType = ml, e.lanes = o, e;
      case vl:
        return e = en(13, n, t, i), e.elementType = vl, e.lanes = o, e;
      case yl:
        return e = en(19, n, t, i), e.elementType = yl, e.lanes = o, e;
      case Hf:
        return fa(n, i, o, t);
      default:
        if (typeof e == "object" && e !== null) switch (e.$$typeof) {
          case $f:
            s = 10;
            break e;
          case jf:
            s = 9;
            break e;
          case xu:
            s = 11;
            break e;
          case Cu:
            s = 14;
            break e;
          case nr:
            s = 16, r = null;
            break e;
        }
        throw Error(W(130, e == null ? e : typeof e, ""));
    }
    return t = en(s, n, t, i), t.elementType = e, t.type = r, t.lanes = o, t;
  }
  function Ir(e, t, n, r) {
    return e = en(7, e, r, t), e.lanes = n, e;
  }
  function fa(e, t, n, r) {
    return e = en(22, e, r, t), e.elementType = Hf, e.lanes = n, e.stateNode = {
      isHidden: false
    }, e;
  }
  function Xa(e, t, n) {
    return e = en(6, e, null, t), e.lanes = n, e;
  }
  function Za(e, t, n) {
    return t = en(4, e.children !== null ? e.children : [], e.key, t), t.lanes = n, t.stateNode = {
      containerInfo: e.containerInfo,
      pendingChildren: null,
      implementation: e.implementation
    }, t;
  }
  function By(e, t, n, r, i) {
    this.tag = t, this.containerInfo = e, this.finishedWork = this.pingCache = this.current = this.pendingChildren = null, this.timeoutHandle = -1, this.callbackNode = this.pendingContext = this.context = null, this.callbackPriority = 0, this.eventTimes = Ia(0), this.expirationTimes = Ia(-1), this.entangledLanes = this.finishedLanes = this.mutableReadLanes = this.expiredLanes = this.pingedLanes = this.suspendedLanes = this.pendingLanes = 0, this.entanglements = Ia(0), this.identifierPrefix = r, this.onRecoverableError = i, this.mutableSourceEagerHydrationData = null;
  }
  function ac(e, t, n, r, i, o, s, a, l) {
    return e = new By(e, t, n, a, l), t === 1 ? (t = 1, o === true && (t |= 8)) : t = 0, o = en(3, null, null, t), e.current = o, o.stateNode = e, o.memoizedState = {
      element: r,
      isDehydrated: n,
      cache: null,
      transitions: null,
      pendingSuspenseBoundaries: null
    }, Hu(o), e;
  }
  function My(e, t, n) {
    var r = 3 < arguments.length && arguments[3] !== void 0 ? arguments[3] : null;
    return {
      $$typeof: jr,
      key: r == null ? null : "" + r,
      children: e,
      containerInfo: t,
      implementation: n
    };
  }
  function Fp(e) {
    if (!e) return vr;
    e = e._reactInternals;
    e: {
      if (Gr(e) !== e || e.tag !== 1) throw Error(W(170));
      var t = e;
      do {
        switch (t.tag) {
          case 3:
            t = t.stateNode.context;
            break e;
          case 1:
            if (Bt(t.type)) {
              t = t.stateNode.__reactInternalMemoizedMergedChildContext;
              break e;
            }
        }
        t = t.return;
      } while (t !== null);
      throw Error(W(171));
    }
    if (e.tag === 1) {
      var n = e.type;
      if (Bt(n)) return Fh(e, n, t);
    }
    return t;
  }
  function zp(e, t, n, r, i, o, s, a, l) {
    return e = ac(n, r, true, e, i, o, s, a, l), e.context = Fp(null), n = e.current, r = Lt(), i = pr(n), o = $n(r, i), o.callback = t ?? null, fr(n, o, i), e.current.lanes = i, Ao(e, i, r), Mt(e, r), e;
  }
  function ha(e, t, n, r) {
    var i = t.current, o = Lt(), s = pr(i);
    return n = Fp(n), t.context === null ? t.context = n : t.pendingContext = n, t = $n(o, s), t.payload = {
      element: e
    }, r = r === void 0 ? null : r, r !== null && (t.callback = r), e = fr(i, t, s), e !== null && (En(e, i, s, o), ps(e, i, s)), s;
  }
  function Ks(e) {
    if (e = e.current, !e.child) return null;
    switch (e.child.tag) {
      case 5:
        return e.child.stateNode;
      default:
        return e.child.stateNode;
    }
  }
  function Ld(e, t) {
    if (e = e.memoizedState, e !== null && e.dehydrated !== null) {
      var n = e.retryLane;
      e.retryLane = n !== 0 && n < t ? n : t;
    }
  }
  function lc(e, t) {
    Ld(e, t), (e = e.alternate) && Ld(e, t);
  }
  function $y() {
    return null;
  }
  var Op = typeof reportError == "function" ? reportError : function(e) {
    console.error(e);
  };
  function uc(e) {
    this._internalRoot = e;
  }
  pa.prototype.render = uc.prototype.render = function(e) {
    var t = this._internalRoot;
    if (t === null) throw Error(W(409));
    ha(e, t, null, null);
  };
  pa.prototype.unmount = uc.prototype.unmount = function() {
    var e = this._internalRoot;
    if (e !== null) {
      this._internalRoot = null;
      var t = e.containerInfo;
      zr(function() {
        ha(null, e, null, null);
      }), t[Wn] = null;
    }
  };
  function pa(e) {
    this._internalRoot = e;
  }
  pa.prototype.unstable_scheduleHydration = function(e) {
    if (e) {
      var t = ph();
      e = {
        blockedOn: null,
        target: e,
        priority: t
      };
      for (var n = 0; n < ir.length && t !== 0 && t < ir[n].priority; n++) ;
      ir.splice(n, 0, e), n === 0 && mh(e);
    }
  };
  function cc(e) {
    return !(!e || e.nodeType !== 1 && e.nodeType !== 9 && e.nodeType !== 11);
  }
  function ga(e) {
    return !(!e || e.nodeType !== 1 && e.nodeType !== 9 && e.nodeType !== 11 && (e.nodeType !== 8 || e.nodeValue !== " react-mount-point-unstable "));
  }
  function Id() {
  }
  function jy(e, t, n, r, i) {
    if (i) {
      if (typeof r == "function") {
        var o = r;
        r = function() {
          var c = Ks(s);
          o.call(c);
        };
      }
      var s = zp(t, r, e, 0, null, false, false, "", Id);
      return e._reactRootContainer = s, e[Wn] = s.current, vo(e.nodeType === 8 ? e.parentNode : e), zr(), s;
    }
    for (; i = e.lastChild; ) e.removeChild(i);
    if (typeof r == "function") {
      var a = r;
      r = function() {
        var c = Ks(l);
        a.call(c);
      };
    }
    var l = ac(e, 0, false, null, null, false, false, "", Id);
    return e._reactRootContainer = l, e[Wn] = l.current, vo(e.nodeType === 8 ? e.parentNode : e), zr(function() {
      ha(t, l, n, r);
    }), l;
  }
  function ma(e, t, n, r, i) {
    var o = n._reactRootContainer;
    if (o) {
      var s = o;
      if (typeof i == "function") {
        var a = i;
        i = function() {
          var l = Ks(s);
          a.call(l);
        };
      }
      ha(t, s, e, i);
    } else s = jy(n, t, e, i, r);
    return Ks(s);
  }
  fh = function(e) {
    switch (e.tag) {
      case 3:
        var t = e.stateNode;
        if (t.current.memoizedState.isDehydrated) {
          var n = Qi(t.pendingLanes);
          n !== 0 && (Au(t, n | 1), Mt(t, Ze()), !(be & 6) && (gi = Ze() + 500, Er()));
        }
        break;
      case 13:
        zr(function() {
          var r = Vn(e, 1);
          if (r !== null) {
            var i = Lt();
            En(r, e, 1, i);
          }
        }), lc(e, 1);
    }
  };
  Lu = function(e) {
    if (e.tag === 13) {
      var t = Vn(e, 134217728);
      if (t !== null) {
        var n = Lt();
        En(t, e, 134217728, n);
      }
      lc(e, 134217728);
    }
  };
  hh = function(e) {
    if (e.tag === 13) {
      var t = pr(e), n = Vn(e, t);
      if (n !== null) {
        var r = Lt();
        En(n, e, t, r);
      }
      lc(e, t);
    }
  };
  ph = function() {
    return De;
  };
  gh = function(e, t) {
    var n = De;
    try {
      return De = e, t();
    } finally {
      De = n;
    }
  };
  Rl = function(e, t, n) {
    switch (t) {
      case "input":
        if (Sl(e, n), t = n.name, n.type === "radio" && t != null) {
          for (n = e; n.parentNode; ) n = n.parentNode;
          for (n = n.querySelectorAll("input[name=" + JSON.stringify("" + t) + '][type="radio"]'), t = 0; t < n.length; t++) {
            var r = n[t];
            if (r !== e && r.form === e.form) {
              var i = sa(r);
              if (!i) throw Error(W(90));
              Vf(r), Sl(r, i);
            }
          }
        }
        break;
      case "textarea":
        Yf(e, n);
        break;
      case "select":
        t = n.value, t != null && ti(e, !!n.multiple, t, false);
    }
  };
  th = rc;
  nh = zr;
  var Hy = {
    usingClientEntryPoint: false,
    Events: [
      Io,
      Yr,
      sa,
      Jf,
      eh,
      rc
    ]
  }, zi = {
    findFiberByHostInstance: Tr,
    bundleType: 0,
    version: "18.3.1",
    rendererPackageName: "react-dom"
  }, Wy = {
    bundleType: zi.bundleType,
    version: zi.version,
    rendererPackageName: zi.rendererPackageName,
    rendererConfig: zi.rendererConfig,
    overrideHookState: null,
    overrideHookStateDeletePath: null,
    overrideHookStateRenamePath: null,
    overrideProps: null,
    overridePropsDeletePath: null,
    overridePropsRenamePath: null,
    setErrorHandler: null,
    setSuspenseHandler: null,
    scheduleUpdate: null,
    currentDispatcherRef: Yn.ReactCurrentDispatcher,
    findHostInstanceByFiber: function(e) {
      return e = oh(e), e === null ? null : e.stateNode;
    },
    findFiberByHostInstance: zi.findFiberByHostInstance || $y,
    findHostInstancesForRefresh: null,
    scheduleRefresh: null,
    scheduleRoot: null,
    setRefreshHandler: null,
    getCurrentFiber: null,
    reconcilerVersion: "18.3.1-next-f1338f8080-20240426"
  };
  if (typeof __REACT_DEVTOOLS_GLOBAL_HOOK__ < "u") {
    var Jo = __REACT_DEVTOOLS_GLOBAL_HOOK__;
    if (!Jo.isDisabled && Jo.supportsFiber) try {
      na = Jo.inject(Wy), An = Jo;
    } catch {
    }
  }
  Kt.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED = Hy;
  Kt.createPortal = function(e, t) {
    var n = 2 < arguments.length && arguments[2] !== void 0 ? arguments[2] : null;
    if (!cc(t)) throw Error(W(200));
    return My(e, t, null, n);
  };
  Kt.createRoot = function(e, t) {
    if (!cc(e)) throw Error(W(299));
    var n = false, r = "", i = Op;
    return t != null && (t.unstable_strictMode === true && (n = true), t.identifierPrefix !== void 0 && (r = t.identifierPrefix), t.onRecoverableError !== void 0 && (i = t.onRecoverableError)), t = ac(e, 1, false, null, null, n, false, r, i), e[Wn] = t.current, vo(e.nodeType === 8 ? e.parentNode : e), new uc(t);
  };
  Kt.findDOMNode = function(e) {
    if (e == null) return null;
    if (e.nodeType === 1) return e;
    var t = e._reactInternals;
    if (t === void 0) throw typeof e.render == "function" ? Error(W(188)) : (e = Object.keys(e).join(","), Error(W(268, e)));
    return e = oh(t), e = e === null ? null : e.stateNode, e;
  };
  Kt.flushSync = function(e) {
    return zr(e);
  };
  Kt.hydrate = function(e, t, n) {
    if (!ga(t)) throw Error(W(200));
    return ma(null, e, t, true, n);
  };
  Kt.hydrateRoot = function(e, t, n) {
    if (!cc(e)) throw Error(W(405));
    var r = n != null && n.hydratedSources || null, i = false, o = "", s = Op;
    if (n != null && (n.unstable_strictMode === true && (i = true), n.identifierPrefix !== void 0 && (o = n.identifierPrefix), n.onRecoverableError !== void 0 && (s = n.onRecoverableError)), t = zp(t, null, e, 1, n ?? null, i, false, o, s), e[Wn] = t.current, vo(e), r) for (e = 0; e < r.length; e++) n = r[e], i = n._getVersion, i = i(n._source), t.mutableSourceEagerHydrationData == null ? t.mutableSourceEagerHydrationData = [
      n,
      i
    ] : t.mutableSourceEagerHydrationData.push(n, i);
    return new pa(t);
  };
  Kt.render = function(e, t, n) {
    if (!ga(t)) throw Error(W(200));
    return ma(null, e, t, false, n);
  };
  Kt.unmountComponentAtNode = function(e) {
    if (!ga(e)) throw Error(W(40));
    return e._reactRootContainer ? (zr(function() {
      ma(null, null, e, false, function() {
        e._reactRootContainer = null, e[Wn] = null;
      });
    }), true) : false;
  };
  Kt.unstable_batchedUpdates = rc;
  Kt.unstable_renderSubtreeIntoContainer = function(e, t, n, r) {
    if (!ga(n)) throw Error(W(200));
    if (e == null || e._reactInternals === void 0) throw Error(W(38));
    return ma(e, t, n, false, r);
  };
  Kt.version = "18.3.1-next-f1338f8080-20240426";
  function Gp() {
    if (!(typeof __REACT_DEVTOOLS_GLOBAL_HOOK__ > "u" || typeof __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE != "function")) try {
      __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE(Gp);
    } catch (e) {
      console.error(e);
    }
  }
  Gp(), Gf.exports = Kt;
  var Vy = Gf.exports, Dd = Vy;
  pl.createRoot = Dd.createRoot, pl.hydrateRoot = Dd.hydrateRoot;
  var Up = {}, va = {};
  va.byteLength = Qy;
  va.toByteArray = Zy;
  va.fromByteArray = e0;
  var Rn = [], Zt = [], Ky = typeof Uint8Array < "u" ? Uint8Array : Array, qa = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  for (var Br = 0, Yy = qa.length; Br < Yy; ++Br) Rn[Br] = qa[Br], Zt[qa.charCodeAt(Br)] = Br;
  Zt[45] = 62;
  Zt[95] = 63;
  function Bp(e) {
    var t = e.length;
    if (t % 4 > 0) throw new Error("Invalid string. Length must be a multiple of 4");
    var n = e.indexOf("=");
    n === -1 && (n = t);
    var r = n === t ? 0 : 4 - n % 4;
    return [
      n,
      r
    ];
  }
  function Qy(e) {
    var t = Bp(e), n = t[0], r = t[1];
    return (n + r) * 3 / 4 - r;
  }
  function Xy(e, t, n) {
    return (t + n) * 3 / 4 - n;
  }
  function Zy(e) {
    var t, n = Bp(e), r = n[0], i = n[1], o = new Ky(Xy(e, r, i)), s = 0, a = i > 0 ? r - 4 : r, l;
    for (l = 0; l < a; l += 4) t = Zt[e.charCodeAt(l)] << 18 | Zt[e.charCodeAt(l + 1)] << 12 | Zt[e.charCodeAt(l + 2)] << 6 | Zt[e.charCodeAt(l + 3)], o[s++] = t >> 16 & 255, o[s++] = t >> 8 & 255, o[s++] = t & 255;
    return i === 2 && (t = Zt[e.charCodeAt(l)] << 2 | Zt[e.charCodeAt(l + 1)] >> 4, o[s++] = t & 255), i === 1 && (t = Zt[e.charCodeAt(l)] << 10 | Zt[e.charCodeAt(l + 1)] << 4 | Zt[e.charCodeAt(l + 2)] >> 2, o[s++] = t >> 8 & 255, o[s++] = t & 255), o;
  }
  function qy(e) {
    return Rn[e >> 18 & 63] + Rn[e >> 12 & 63] + Rn[e >> 6 & 63] + Rn[e & 63];
  }
  function Jy(e, t, n) {
    for (var r, i = [], o = t; o < n; o += 3) r = (e[o] << 16 & 16711680) + (e[o + 1] << 8 & 65280) + (e[o + 2] & 255), i.push(qy(r));
    return i.join("");
  }
  function e0(e) {
    for (var t, n = e.length, r = n % 3, i = [], o = 16383, s = 0, a = n - r; s < a; s += o) i.push(Jy(e, s, s + o > a ? a : s + o));
    return r === 1 ? (t = e[n - 1], i.push(Rn[t >> 2] + Rn[t << 4 & 63] + "==")) : r === 2 && (t = (e[n - 2] << 8) + e[n - 1], i.push(Rn[t >> 10] + Rn[t >> 4 & 63] + Rn[t << 2 & 63] + "=")), i.join("");
  }
  var dc = {};
  dc.read = function(e, t, n, r, i) {
    var o, s, a = i * 8 - r - 1, l = (1 << a) - 1, c = l >> 1, h = -7, f = n ? i - 1 : 0, p = n ? -1 : 1, y = e[t + f];
    for (f += p, o = y & (1 << -h) - 1, y >>= -h, h += a; h > 0; o = o * 256 + e[t + f], f += p, h -= 8) ;
    for (s = o & (1 << -h) - 1, o >>= -h, h += r; h > 0; s = s * 256 + e[t + f], f += p, h -= 8) ;
    if (o === 0) o = 1 - c;
    else {
      if (o === l) return s ? NaN : (y ? -1 : 1) * (1 / 0);
      s = s + Math.pow(2, r), o = o - c;
    }
    return (y ? -1 : 1) * s * Math.pow(2, o - r);
  };
  dc.write = function(e, t, n, r, i, o) {
    var s, a, l, c = o * 8 - i - 1, h = (1 << c) - 1, f = h >> 1, p = i === 23 ? Math.pow(2, -24) - Math.pow(2, -77) : 0, y = r ? 0 : o - 1, k = r ? 1 : -1, b = t < 0 || t === 0 && 1 / t < 0 ? 1 : 0;
    for (t = Math.abs(t), isNaN(t) || t === 1 / 0 ? (a = isNaN(t) ? 1 : 0, s = h) : (s = Math.floor(Math.log(t) / Math.LN2), t * (l = Math.pow(2, -s)) < 1 && (s--, l *= 2), s + f >= 1 ? t += p / l : t += p * Math.pow(2, 1 - f), t * l >= 2 && (s++, l /= 2), s + f >= h ? (a = 0, s = h) : s + f >= 1 ? (a = (t * l - 1) * Math.pow(2, i), s = s + f) : (a = t * Math.pow(2, f - 1) * Math.pow(2, i), s = 0)); i >= 8; e[n + y] = a & 255, y += k, a /= 256, i -= 8) ;
    for (s = s << i | a, c += i; c > 0; e[n + y] = s & 255, y += k, s /= 256, c -= 8) ;
    e[n + y - k] |= b * 128;
  };
  (function(e) {
    const t = va, n = dc, r = typeof Symbol == "function" && typeof Symbol.for == "function" ? Symbol.for("nodejs.util.inspect.custom") : null;
    e.Buffer = a, e.SlowBuffer = m, e.INSPECT_MAX_BYTES = 50;
    const i = 2147483647;
    e.kMaxLength = i, a.TYPED_ARRAY_SUPPORT = o(), !a.TYPED_ARRAY_SUPPORT && typeof console < "u" && typeof console.error == "function" && console.error("This browser lacks typed array (Uint8Array) support which is required by `buffer` v5.x. Use `buffer` v4.x if you require old browser support.");
    function o() {
      try {
        const g = new Uint8Array(1), u = {
          foo: function() {
            return 42;
          }
        };
        return Object.setPrototypeOf(u, Uint8Array.prototype), Object.setPrototypeOf(g, u), g.foo() === 42;
      } catch {
        return false;
      }
    }
    Object.defineProperty(a.prototype, "parent", {
      enumerable: true,
      get: function() {
        if (a.isBuffer(this)) return this.buffer;
      }
    }), Object.defineProperty(a.prototype, "offset", {
      enumerable: true,
      get: function() {
        if (a.isBuffer(this)) return this.byteOffset;
      }
    });
    function s(g) {
      if (g > i) throw new RangeError('The value "' + g + '" is invalid for option "size"');
      const u = new Uint8Array(g);
      return Object.setPrototypeOf(u, a.prototype), u;
    }
    function a(g, u, d) {
      if (typeof g == "number") {
        if (typeof u == "string") throw new TypeError('The "string" argument must be of type string. Received type number');
        return f(g);
      }
      return l(g, u, d);
    }
    a.poolSize = 8192;
    function l(g, u, d) {
      if (typeof g == "string") return p(g, u);
      if (ArrayBuffer.isView(g)) return k(g);
      if (g == null) throw new TypeError("The first argument must be one of type string, Buffer, ArrayBuffer, Array, or Array-like Object. Received type " + typeof g);
      if (He(g, ArrayBuffer) || g && He(g.buffer, ArrayBuffer) || typeof SharedArrayBuffer < "u" && (He(g, SharedArrayBuffer) || g && He(g.buffer, SharedArrayBuffer))) return b(g, u, d);
      if (typeof g == "number") throw new TypeError('The "value" argument must not be of type number. Received type number');
      const w = g.valueOf && g.valueOf();
      if (w != null && w !== g) return a.from(w, u, d);
      const T = I(g);
      if (T) return T;
      if (typeof Symbol < "u" && Symbol.toPrimitive != null && typeof g[Symbol.toPrimitive] == "function") return a.from(g[Symbol.toPrimitive]("string"), u, d);
      throw new TypeError("The first argument must be one of type string, Buffer, ArrayBuffer, Array, or Array-like Object. Received type " + typeof g);
    }
    a.from = function(g, u, d) {
      return l(g, u, d);
    }, Object.setPrototypeOf(a.prototype, Uint8Array.prototype), Object.setPrototypeOf(a, Uint8Array);
    function c(g) {
      if (typeof g != "number") throw new TypeError('"size" argument must be of type number');
      if (g < 0) throw new RangeError('The value "' + g + '" is invalid for option "size"');
    }
    function h(g, u, d) {
      return c(g), g <= 0 ? s(g) : u !== void 0 ? typeof d == "string" ? s(g).fill(u, d) : s(g).fill(u) : s(g);
    }
    a.alloc = function(g, u, d) {
      return h(g, u, d);
    };
    function f(g) {
      return c(g), s(g < 0 ? 0 : _(g) | 0);
    }
    a.allocUnsafe = function(g) {
      return f(g);
    }, a.allocUnsafeSlow = function(g) {
      return f(g);
    };
    function p(g, u) {
      if ((typeof u != "string" || u === "") && (u = "utf8"), !a.isEncoding(u)) throw new TypeError("Unknown encoding: " + u);
      const d = v(g, u) | 0;
      let w = s(d);
      const T = w.write(g, u);
      return T !== d && (w = w.slice(0, T)), w;
    }
    function y(g) {
      const u = g.length < 0 ? 0 : _(g.length) | 0, d = s(u);
      for (let w = 0; w < u; w += 1) d[w] = g[w] & 255;
      return d;
    }
    function k(g) {
      if (He(g, Uint8Array)) {
        const u = new Uint8Array(g);
        return b(u.buffer, u.byteOffset, u.byteLength);
      }
      return y(g);
    }
    function b(g, u, d) {
      if (u < 0 || g.byteLength < u) throw new RangeError('"offset" is outside of buffer bounds');
      if (g.byteLength < u + (d || 0)) throw new RangeError('"length" is outside of buffer bounds');
      let w;
      return u === void 0 && d === void 0 ? w = new Uint8Array(g) : d === void 0 ? w = new Uint8Array(g, u) : w = new Uint8Array(g, u, d), Object.setPrototypeOf(w, a.prototype), w;
    }
    function I(g) {
      if (a.isBuffer(g)) {
        const u = _(g.length) | 0, d = s(u);
        return d.length === 0 || g.copy(d, 0, 0, u), d;
      }
      if (g.length !== void 0) return typeof g.length != "number" || Pt(g.length) ? s(0) : y(g);
      if (g.type === "Buffer" && Array.isArray(g.data)) return y(g.data);
    }
    function _(g) {
      if (g >= i) throw new RangeError("Attempt to allocate Buffer larger than maximum size: 0x" + i.toString(16) + " bytes");
      return g | 0;
    }
    function m(g) {
      return +g != g && (g = 0), a.alloc(+g);
    }
    a.isBuffer = function(u) {
      return u != null && u._isBuffer === true && u !== a.prototype;
    }, a.compare = function(u, d) {
      if (He(u, Uint8Array) && (u = a.from(u, u.offset, u.byteLength)), He(d, Uint8Array) && (d = a.from(d, d.offset, d.byteLength)), !a.isBuffer(u) || !a.isBuffer(d)) throw new TypeError('The "buf1", "buf2" arguments must be one of type Buffer or Uint8Array');
      if (u === d) return 0;
      let w = u.length, T = d.length;
      for (let P = 0, G = Math.min(w, T); P < G; ++P) if (u[P] !== d[P]) {
        w = u[P], T = d[P];
        break;
      }
      return w < T ? -1 : T < w ? 1 : 0;
    }, a.isEncoding = function(u) {
      switch (String(u).toLowerCase()) {
        case "hex":
        case "utf8":
        case "utf-8":
        case "ascii":
        case "latin1":
        case "binary":
        case "base64":
        case "ucs2":
        case "ucs-2":
        case "utf16le":
        case "utf-16le":
          return true;
        default:
          return false;
      }
    }, a.concat = function(u, d) {
      if (!Array.isArray(u)) throw new TypeError('"list" argument must be an Array of Buffers');
      if (u.length === 0) return a.alloc(0);
      let w;
      if (d === void 0) for (d = 0, w = 0; w < u.length; ++w) d += u[w].length;
      const T = a.allocUnsafe(d);
      let P = 0;
      for (w = 0; w < u.length; ++w) {
        let G = u[w];
        if (He(G, Uint8Array)) P + G.length > T.length ? (a.isBuffer(G) || (G = a.from(G)), G.copy(T, P)) : Uint8Array.prototype.set.call(T, G, P);
        else if (a.isBuffer(G)) G.copy(T, P);
        else throw new TypeError('"list" argument must be an Array of Buffers');
        P += G.length;
      }
      return T;
    };
    function v(g, u) {
      if (a.isBuffer(g)) return g.length;
      if (ArrayBuffer.isView(g) || He(g, ArrayBuffer)) return g.byteLength;
      if (typeof g != "string") throw new TypeError('The "string" argument must be one of type string, Buffer, or ArrayBuffer. Received type ' + typeof g);
      const d = g.length, w = arguments.length > 2 && arguments[2] === true;
      if (!w && d === 0) return 0;
      let T = false;
      for (; ; ) switch (u) {
        case "ascii":
        case "latin1":
        case "binary":
          return d;
        case "utf8":
        case "utf-8":
          return he(g).length;
        case "ucs2":
        case "ucs-2":
        case "utf16le":
        case "utf-16le":
          return d * 2;
        case "hex":
          return d >>> 1;
        case "base64":
          return se(g).length;
        default:
          if (T) return w ? -1 : he(g).length;
          u = ("" + u).toLowerCase(), T = true;
      }
    }
    a.byteLength = v;
    function E(g, u, d) {
      let w = false;
      if ((u === void 0 || u < 0) && (u = 0), u > this.length || ((d === void 0 || d > this.length) && (d = this.length), d <= 0) || (d >>>= 0, u >>>= 0, d <= u)) return "";
      for (g || (g = "utf8"); ; ) switch (g) {
        case "hex":
          return j(this, u, d);
        case "utf8":
        case "utf-8":
          return O(this, u, d);
        case "ascii":
          return J(this, u, d);
        case "latin1":
        case "binary":
          return S(this, u, d);
        case "base64":
          return K(this, u, d);
        case "ucs2":
        case "ucs-2":
        case "utf16le":
        case "utf-16le":
          return H(this, u, d);
        default:
          if (w) throw new TypeError("Unknown encoding: " + g);
          g = (g + "").toLowerCase(), w = true;
      }
    }
    a.prototype._isBuffer = true;
    function A(g, u, d) {
      const w = g[u];
      g[u] = g[d], g[d] = w;
    }
    a.prototype.swap16 = function() {
      const u = this.length;
      if (u % 2 !== 0) throw new RangeError("Buffer size must be a multiple of 16-bits");
      for (let d = 0; d < u; d += 2) A(this, d, d + 1);
      return this;
    }, a.prototype.swap32 = function() {
      const u = this.length;
      if (u % 4 !== 0) throw new RangeError("Buffer size must be a multiple of 32-bits");
      for (let d = 0; d < u; d += 4) A(this, d, d + 3), A(this, d + 1, d + 2);
      return this;
    }, a.prototype.swap64 = function() {
      const u = this.length;
      if (u % 8 !== 0) throw new RangeError("Buffer size must be a multiple of 64-bits");
      for (let d = 0; d < u; d += 8) A(this, d, d + 7), A(this, d + 1, d + 6), A(this, d + 2, d + 5), A(this, d + 3, d + 4);
      return this;
    }, a.prototype.toString = function() {
      const u = this.length;
      return u === 0 ? "" : arguments.length === 0 ? O(this, 0, u) : E.apply(this, arguments);
    }, a.prototype.toLocaleString = a.prototype.toString, a.prototype.equals = function(u) {
      if (!a.isBuffer(u)) throw new TypeError("Argument must be a Buffer");
      return this === u ? true : a.compare(this, u) === 0;
    }, a.prototype.inspect = function() {
      let u = "";
      const d = e.INSPECT_MAX_BYTES;
      return u = this.toString("hex", 0, d).replace(/(.{2})/g, "$1 ").trim(), this.length > d && (u += " ... "), "<Buffer " + u + ">";
    }, r && (a.prototype[r] = a.prototype.inspect), a.prototype.compare = function(u, d, w, T, P) {
      if (He(u, Uint8Array) && (u = a.from(u, u.offset, u.byteLength)), !a.isBuffer(u)) throw new TypeError('The "target" argument must be one of type Buffer or Uint8Array. Received type ' + typeof u);
      if (d === void 0 && (d = 0), w === void 0 && (w = u ? u.length : 0), T === void 0 && (T = 0), P === void 0 && (P = this.length), d < 0 || w > u.length || T < 0 || P > this.length) throw new RangeError("out of range index");
      if (T >= P && d >= w) return 0;
      if (T >= P) return -1;
      if (d >= w) return 1;
      if (d >>>= 0, w >>>= 0, T >>>= 0, P >>>= 0, this === u) return 0;
      let G = P - T, fe = w - d;
      const ke = Math.min(G, fe), Ce = this.slice(T, P), xe = u.slice(d, w);
      for (let Le = 0; Le < ke; ++Le) if (Ce[Le] !== xe[Le]) {
        G = Ce[Le], fe = xe[Le];
        break;
      }
      return G < fe ? -1 : fe < G ? 1 : 0;
    };
    function F(g, u, d, w, T) {
      if (g.length === 0) return -1;
      if (typeof d == "string" ? (w = d, d = 0) : d > 2147483647 ? d = 2147483647 : d < -2147483648 && (d = -2147483648), d = +d, Pt(d) && (d = T ? 0 : g.length - 1), d < 0 && (d = g.length + d), d >= g.length) {
        if (T) return -1;
        d = g.length - 1;
      } else if (d < 0) if (T) d = 0;
      else return -1;
      if (typeof u == "string" && (u = a.from(u, w)), a.isBuffer(u)) return u.length === 0 ? -1 : R(g, u, d, w, T);
      if (typeof u == "number") return u = u & 255, typeof Uint8Array.prototype.indexOf == "function" ? T ? Uint8Array.prototype.indexOf.call(g, u, d) : Uint8Array.prototype.lastIndexOf.call(g, u, d) : R(g, [
        u
      ], d, w, T);
      throw new TypeError("val must be string, number or Buffer");
    }
    function R(g, u, d, w, T) {
      let P = 1, G = g.length, fe = u.length;
      if (w !== void 0 && (w = String(w).toLowerCase(), w === "ucs2" || w === "ucs-2" || w === "utf16le" || w === "utf-16le")) {
        if (g.length < 2 || u.length < 2) return -1;
        P = 2, G /= 2, fe /= 2, d /= 2;
      }
      function ke(xe, Le) {
        return P === 1 ? xe[Le] : xe.readUInt16BE(Le * P);
      }
      let Ce;
      if (T) {
        let xe = -1;
        for (Ce = d; Ce < G; Ce++) if (ke(g, Ce) === ke(u, xe === -1 ? 0 : Ce - xe)) {
          if (xe === -1 && (xe = Ce), Ce - xe + 1 === fe) return xe * P;
        } else xe !== -1 && (Ce -= Ce - xe), xe = -1;
      } else for (d + fe > G && (d = G - fe), Ce = d; Ce >= 0; Ce--) {
        let xe = true;
        for (let Le = 0; Le < fe; Le++) if (ke(g, Ce + Le) !== ke(u, Le)) {
          xe = false;
          break;
        }
        if (xe) return Ce;
      }
      return -1;
    }
    a.prototype.includes = function(u, d, w) {
      return this.indexOf(u, d, w) !== -1;
    }, a.prototype.indexOf = function(u, d, w) {
      return F(this, u, d, w, true);
    }, a.prototype.lastIndexOf = function(u, d, w) {
      return F(this, u, d, w, false);
    };
    function L(g, u, d, w) {
      d = Number(d) || 0;
      const T = g.length - d;
      w ? (w = Number(w), w > T && (w = T)) : w = T;
      const P = u.length;
      w > P / 2 && (w = P / 2);
      let G;
      for (G = 0; G < w; ++G) {
        const fe = parseInt(u.substr(G * 2, 2), 16);
        if (Pt(fe)) return G;
        g[d + G] = fe;
      }
      return G;
    }
    function C(g, u, d, w) {
      return U(he(u, g.length - d), g, d, w);
    }
    function N(g, u, d, w) {
      return U(vt(u), g, d, w);
    }
    function V(g, u, d, w) {
      return U(se(u), g, d, w);
    }
    function B(g, u, d, w) {
      return U(le(u, g.length - d), g, d, w);
    }
    a.prototype.write = function(u, d, w, T) {
      if (d === void 0) T = "utf8", w = this.length, d = 0;
      else if (w === void 0 && typeof d == "string") T = d, w = this.length, d = 0;
      else if (isFinite(d)) d = d >>> 0, isFinite(w) ? (w = w >>> 0, T === void 0 && (T = "utf8")) : (T = w, w = void 0);
      else throw new Error("Buffer.write(string, encoding, offset[, length]) is no longer supported");
      const P = this.length - d;
      if ((w === void 0 || w > P) && (w = P), u.length > 0 && (w < 0 || d < 0) || d > this.length) throw new RangeError("Attempt to write outside buffer bounds");
      T || (T = "utf8");
      let G = false;
      for (; ; ) switch (T) {
        case "hex":
          return L(this, u, d, w);
        case "utf8":
        case "utf-8":
          return C(this, u, d, w);
        case "ascii":
        case "latin1":
        case "binary":
          return N(this, u, d, w);
        case "base64":
          return V(this, u, d, w);
        case "ucs2":
        case "ucs-2":
        case "utf16le":
        case "utf-16le":
          return B(this, u, d, w);
        default:
          if (G) throw new TypeError("Unknown encoding: " + T);
          T = ("" + T).toLowerCase(), G = true;
      }
    }, a.prototype.toJSON = function() {
      return {
        type: "Buffer",
        data: Array.prototype.slice.call(this._arr || this, 0)
      };
    };
    function K(g, u, d) {
      return u === 0 && d === g.length ? t.fromByteArray(g) : t.fromByteArray(g.slice(u, d));
    }
    function O(g, u, d) {
      d = Math.min(g.length, d);
      const w = [];
      let T = u;
      for (; T < d; ) {
        const P = g[T];
        let G = null, fe = P > 239 ? 4 : P > 223 ? 3 : P > 191 ? 2 : 1;
        if (T + fe <= d) {
          let ke, Ce, xe, Le;
          switch (fe) {
            case 1:
              P < 128 && (G = P);
              break;
            case 2:
              ke = g[T + 1], (ke & 192) === 128 && (Le = (P & 31) << 6 | ke & 63, Le > 127 && (G = Le));
              break;
            case 3:
              ke = g[T + 1], Ce = g[T + 2], (ke & 192) === 128 && (Ce & 192) === 128 && (Le = (P & 15) << 12 | (ke & 63) << 6 | Ce & 63, Le > 2047 && (Le < 55296 || Le > 57343) && (G = Le));
              break;
            case 4:
              ke = g[T + 1], Ce = g[T + 2], xe = g[T + 3], (ke & 192) === 128 && (Ce & 192) === 128 && (xe & 192) === 128 && (Le = (P & 15) << 18 | (ke & 63) << 12 | (Ce & 63) << 6 | xe & 63, Le > 65535 && Le < 1114112 && (G = Le));
          }
        }
        G === null ? (G = 65533, fe = 1) : G > 65535 && (G -= 65536, w.push(G >>> 10 & 1023 | 55296), G = 56320 | G & 1023), w.push(G), T += fe;
      }
      return ae(w);
    }
    const re = 4096;
    function ae(g) {
      const u = g.length;
      if (u <= re) return String.fromCharCode.apply(String, g);
      let d = "", w = 0;
      for (; w < u; ) d += String.fromCharCode.apply(String, g.slice(w, w += re));
      return d;
    }
    function J(g, u, d) {
      let w = "";
      d = Math.min(g.length, d);
      for (let T = u; T < d; ++T) w += String.fromCharCode(g[T] & 127);
      return w;
    }
    function S(g, u, d) {
      let w = "";
      d = Math.min(g.length, d);
      for (let T = u; T < d; ++T) w += String.fromCharCode(g[T]);
      return w;
    }
    function j(g, u, d) {
      const w = g.length;
      (!u || u < 0) && (u = 0), (!d || d < 0 || d > w) && (d = w);
      let T = "";
      for (let P = u; P < d; ++P) T += ln[g[P]];
      return T;
    }
    function H(g, u, d) {
      const w = g.slice(u, d);
      let T = "";
      for (let P = 0; P < w.length - 1; P += 2) T += String.fromCharCode(w[P] + w[P + 1] * 256);
      return T;
    }
    a.prototype.slice = function(u, d) {
      const w = this.length;
      u = ~~u, d = d === void 0 ? w : ~~d, u < 0 ? (u += w, u < 0 && (u = 0)) : u > w && (u = w), d < 0 ? (d += w, d < 0 && (d = 0)) : d > w && (d = w), d < u && (d = u);
      const T = this.subarray(u, d);
      return Object.setPrototypeOf(T, a.prototype), T;
    };
    function D(g, u, d) {
      if (g % 1 !== 0 || g < 0) throw new RangeError("offset is not uint");
      if (g + u > d) throw new RangeError("Trying to access beyond buffer length");
    }
    a.prototype.readUintLE = a.prototype.readUIntLE = function(u, d, w) {
      u = u >>> 0, d = d >>> 0, w || D(u, d, this.length);
      let T = this[u], P = 1, G = 0;
      for (; ++G < d && (P *= 256); ) T += this[u + G] * P;
      return T;
    }, a.prototype.readUintBE = a.prototype.readUIntBE = function(u, d, w) {
      u = u >>> 0, d = d >>> 0, w || D(u, d, this.length);
      let T = this[u + --d], P = 1;
      for (; d > 0 && (P *= 256); ) T += this[u + --d] * P;
      return T;
    }, a.prototype.readUint8 = a.prototype.readUInt8 = function(u, d) {
      return u = u >>> 0, d || D(u, 1, this.length), this[u];
    }, a.prototype.readUint16LE = a.prototype.readUInt16LE = function(u, d) {
      return u = u >>> 0, d || D(u, 2, this.length), this[u] | this[u + 1] << 8;
    }, a.prototype.readUint16BE = a.prototype.readUInt16BE = function(u, d) {
      return u = u >>> 0, d || D(u, 2, this.length), this[u] << 8 | this[u + 1];
    }, a.prototype.readUint32LE = a.prototype.readUInt32LE = function(u, d) {
      return u = u >>> 0, d || D(u, 4, this.length), (this[u] | this[u + 1] << 8 | this[u + 2] << 16) + this[u + 3] * 16777216;
    }, a.prototype.readUint32BE = a.prototype.readUInt32BE = function(u, d) {
      return u = u >>> 0, d || D(u, 4, this.length), this[u] * 16777216 + (this[u + 1] << 16 | this[u + 2] << 8 | this[u + 3]);
    }, a.prototype.readBigUInt64LE = at(function(u) {
      u = u >>> 0, mt(u, "offset");
      const d = this[u], w = this[u + 7];
      (d === void 0 || w === void 0) && Xe(u, this.length - 8);
      const T = d + this[++u] * 2 ** 8 + this[++u] * 2 ** 16 + this[++u] * 2 ** 24, P = this[++u] + this[++u] * 2 ** 8 + this[++u] * 2 ** 16 + w * 2 ** 24;
      return BigInt(T) + (BigInt(P) << BigInt(32));
    }), a.prototype.readBigUInt64BE = at(function(u) {
      u = u >>> 0, mt(u, "offset");
      const d = this[u], w = this[u + 7];
      (d === void 0 || w === void 0) && Xe(u, this.length - 8);
      const T = d * 2 ** 24 + this[++u] * 2 ** 16 + this[++u] * 2 ** 8 + this[++u], P = this[++u] * 2 ** 24 + this[++u] * 2 ** 16 + this[++u] * 2 ** 8 + w;
      return (BigInt(T) << BigInt(32)) + BigInt(P);
    }), a.prototype.readIntLE = function(u, d, w) {
      u = u >>> 0, d = d >>> 0, w || D(u, d, this.length);
      let T = this[u], P = 1, G = 0;
      for (; ++G < d && (P *= 256); ) T += this[u + G] * P;
      return P *= 128, T >= P && (T -= Math.pow(2, 8 * d)), T;
    }, a.prototype.readIntBE = function(u, d, w) {
      u = u >>> 0, d = d >>> 0, w || D(u, d, this.length);
      let T = d, P = 1, G = this[u + --T];
      for (; T > 0 && (P *= 256); ) G += this[u + --T] * P;
      return P *= 128, G >= P && (G -= Math.pow(2, 8 * d)), G;
    }, a.prototype.readInt8 = function(u, d) {
      return u = u >>> 0, d || D(u, 1, this.length), this[u] & 128 ? (255 - this[u] + 1) * -1 : this[u];
    }, a.prototype.readInt16LE = function(u, d) {
      u = u >>> 0, d || D(u, 2, this.length);
      const w = this[u] | this[u + 1] << 8;
      return w & 32768 ? w | 4294901760 : w;
    }, a.prototype.readInt16BE = function(u, d) {
      u = u >>> 0, d || D(u, 2, this.length);
      const w = this[u + 1] | this[u] << 8;
      return w & 32768 ? w | 4294901760 : w;
    }, a.prototype.readInt32LE = function(u, d) {
      return u = u >>> 0, d || D(u, 4, this.length), this[u] | this[u + 1] << 8 | this[u + 2] << 16 | this[u + 3] << 24;
    }, a.prototype.readInt32BE = function(u, d) {
      return u = u >>> 0, d || D(u, 4, this.length), this[u] << 24 | this[u + 1] << 16 | this[u + 2] << 8 | this[u + 3];
    }, a.prototype.readBigInt64LE = at(function(u) {
      u = u >>> 0, mt(u, "offset");
      const d = this[u], w = this[u + 7];
      (d === void 0 || w === void 0) && Xe(u, this.length - 8);
      const T = this[u + 4] + this[u + 5] * 2 ** 8 + this[u + 6] * 2 ** 16 + (w << 24);
      return (BigInt(T) << BigInt(32)) + BigInt(d + this[++u] * 2 ** 8 + this[++u] * 2 ** 16 + this[++u] * 2 ** 24);
    }), a.prototype.readBigInt64BE = at(function(u) {
      u = u >>> 0, mt(u, "offset");
      const d = this[u], w = this[u + 7];
      (d === void 0 || w === void 0) && Xe(u, this.length - 8);
      const T = (d << 24) + this[++u] * 2 ** 16 + this[++u] * 2 ** 8 + this[++u];
      return (BigInt(T) << BigInt(32)) + BigInt(this[++u] * 2 ** 24 + this[++u] * 2 ** 16 + this[++u] * 2 ** 8 + w);
    }), a.prototype.readFloatLE = function(u, d) {
      return u = u >>> 0, d || D(u, 4, this.length), n.read(this, u, true, 23, 4);
    }, a.prototype.readFloatBE = function(u, d) {
      return u = u >>> 0, d || D(u, 4, this.length), n.read(this, u, false, 23, 4);
    }, a.prototype.readDoubleLE = function(u, d) {
      return u = u >>> 0, d || D(u, 8, this.length), n.read(this, u, true, 52, 8);
    }, a.prototype.readDoubleBE = function(u, d) {
      return u = u >>> 0, d || D(u, 8, this.length), n.read(this, u, false, 52, 8);
    };
    function x(g, u, d, w, T, P) {
      if (!a.isBuffer(g)) throw new TypeError('"buffer" argument must be a Buffer instance');
      if (u > T || u < P) throw new RangeError('"value" argument is out of bounds');
      if (d + w > g.length) throw new RangeError("Index out of range");
    }
    a.prototype.writeUintLE = a.prototype.writeUIntLE = function(u, d, w, T) {
      if (u = +u, d = d >>> 0, w = w >>> 0, !T) {
        const fe = Math.pow(2, 8 * w) - 1;
        x(this, u, d, w, fe, 0);
      }
      let P = 1, G = 0;
      for (this[d] = u & 255; ++G < w && (P *= 256); ) this[d + G] = u / P & 255;
      return d + w;
    }, a.prototype.writeUintBE = a.prototype.writeUIntBE = function(u, d, w, T) {
      if (u = +u, d = d >>> 0, w = w >>> 0, !T) {
        const fe = Math.pow(2, 8 * w) - 1;
        x(this, u, d, w, fe, 0);
      }
      let P = w - 1, G = 1;
      for (this[d + P] = u & 255; --P >= 0 && (G *= 256); ) this[d + P] = u / G & 255;
      return d + w;
    }, a.prototype.writeUint8 = a.prototype.writeUInt8 = function(u, d, w) {
      return u = +u, d = d >>> 0, w || x(this, u, d, 1, 255, 0), this[d] = u & 255, d + 1;
    }, a.prototype.writeUint16LE = a.prototype.writeUInt16LE = function(u, d, w) {
      return u = +u, d = d >>> 0, w || x(this, u, d, 2, 65535, 0), this[d] = u & 255, this[d + 1] = u >>> 8, d + 2;
    }, a.prototype.writeUint16BE = a.prototype.writeUInt16BE = function(u, d, w) {
      return u = +u, d = d >>> 0, w || x(this, u, d, 2, 65535, 0), this[d] = u >>> 8, this[d + 1] = u & 255, d + 2;
    }, a.prototype.writeUint32LE = a.prototype.writeUInt32LE = function(u, d, w) {
      return u = +u, d = d >>> 0, w || x(this, u, d, 4, 4294967295, 0), this[d + 3] = u >>> 24, this[d + 2] = u >>> 16, this[d + 1] = u >>> 8, this[d] = u & 255, d + 4;
    }, a.prototype.writeUint32BE = a.prototype.writeUInt32BE = function(u, d, w) {
      return u = +u, d = d >>> 0, w || x(this, u, d, 4, 4294967295, 0), this[d] = u >>> 24, this[d + 1] = u >>> 16, this[d + 2] = u >>> 8, this[d + 3] = u & 255, d + 4;
    };
    function Q(g, u, d, w, T) {
      st(u, w, T, g, d, 7);
      let P = Number(u & BigInt(4294967295));
      g[d++] = P, P = P >> 8, g[d++] = P, P = P >> 8, g[d++] = P, P = P >> 8, g[d++] = P;
      let G = Number(u >> BigInt(32) & BigInt(4294967295));
      return g[d++] = G, G = G >> 8, g[d++] = G, G = G >> 8, g[d++] = G, G = G >> 8, g[d++] = G, d;
    }
    function ie(g, u, d, w, T) {
      st(u, w, T, g, d, 7);
      let P = Number(u & BigInt(4294967295));
      g[d + 7] = P, P = P >> 8, g[d + 6] = P, P = P >> 8, g[d + 5] = P, P = P >> 8, g[d + 4] = P;
      let G = Number(u >> BigInt(32) & BigInt(4294967295));
      return g[d + 3] = G, G = G >> 8, g[d + 2] = G, G = G >> 8, g[d + 1] = G, G = G >> 8, g[d] = G, d + 8;
    }
    a.prototype.writeBigUInt64LE = at(function(u, d = 0) {
      return Q(this, u, d, BigInt(0), BigInt("0xffffffffffffffff"));
    }), a.prototype.writeBigUInt64BE = at(function(u, d = 0) {
      return ie(this, u, d, BigInt(0), BigInt("0xffffffffffffffff"));
    }), a.prototype.writeIntLE = function(u, d, w, T) {
      if (u = +u, d = d >>> 0, !T) {
        const ke = Math.pow(2, 8 * w - 1);
        x(this, u, d, w, ke - 1, -ke);
      }
      let P = 0, G = 1, fe = 0;
      for (this[d] = u & 255; ++P < w && (G *= 256); ) u < 0 && fe === 0 && this[d + P - 1] !== 0 && (fe = 1), this[d + P] = (u / G >> 0) - fe & 255;
      return d + w;
    }, a.prototype.writeIntBE = function(u, d, w, T) {
      if (u = +u, d = d >>> 0, !T) {
        const ke = Math.pow(2, 8 * w - 1);
        x(this, u, d, w, ke - 1, -ke);
      }
      let P = w - 1, G = 1, fe = 0;
      for (this[d + P] = u & 255; --P >= 0 && (G *= 256); ) u < 0 && fe === 0 && this[d + P + 1] !== 0 && (fe = 1), this[d + P] = (u / G >> 0) - fe & 255;
      return d + w;
    }, a.prototype.writeInt8 = function(u, d, w) {
      return u = +u, d = d >>> 0, w || x(this, u, d, 1, 127, -128), u < 0 && (u = 255 + u + 1), this[d] = u & 255, d + 1;
    }, a.prototype.writeInt16LE = function(u, d, w) {
      return u = +u, d = d >>> 0, w || x(this, u, d, 2, 32767, -32768), this[d] = u & 255, this[d + 1] = u >>> 8, d + 2;
    }, a.prototype.writeInt16BE = function(u, d, w) {
      return u = +u, d = d >>> 0, w || x(this, u, d, 2, 32767, -32768), this[d] = u >>> 8, this[d + 1] = u & 255, d + 2;
    }, a.prototype.writeInt32LE = function(u, d, w) {
      return u = +u, d = d >>> 0, w || x(this, u, d, 4, 2147483647, -2147483648), this[d] = u & 255, this[d + 1] = u >>> 8, this[d + 2] = u >>> 16, this[d + 3] = u >>> 24, d + 4;
    }, a.prototype.writeInt32BE = function(u, d, w) {
      return u = +u, d = d >>> 0, w || x(this, u, d, 4, 2147483647, -2147483648), u < 0 && (u = 4294967295 + u + 1), this[d] = u >>> 24, this[d + 1] = u >>> 16, this[d + 2] = u >>> 8, this[d + 3] = u & 255, d + 4;
    }, a.prototype.writeBigInt64LE = at(function(u, d = 0) {
      return Q(this, u, d, -BigInt("0x8000000000000000"), BigInt("0x7fffffffffffffff"));
    }), a.prototype.writeBigInt64BE = at(function(u, d = 0) {
      return ie(this, u, d, -BigInt("0x8000000000000000"), BigInt("0x7fffffffffffffff"));
    });
    function _e(g, u, d, w, T, P) {
      if (d + w > g.length) throw new RangeError("Index out of range");
      if (d < 0) throw new RangeError("Index out of range");
    }
    function Se(g, u, d, w, T) {
      return u = +u, d = d >>> 0, T || _e(g, u, d, 4), n.write(g, u, d, w, 23, 4), d + 4;
    }
    a.prototype.writeFloatLE = function(u, d, w) {
      return Se(this, u, d, true, w);
    }, a.prototype.writeFloatBE = function(u, d, w) {
      return Se(this, u, d, false, w);
    };
    function oe(g, u, d, w, T) {
      return u = +u, d = d >>> 0, T || _e(g, u, d, 8), n.write(g, u, d, w, 52, 8), d + 8;
    }
    a.prototype.writeDoubleLE = function(u, d, w) {
      return oe(this, u, d, true, w);
    }, a.prototype.writeDoubleBE = function(u, d, w) {
      return oe(this, u, d, false, w);
    }, a.prototype.copy = function(u, d, w, T) {
      if (!a.isBuffer(u)) throw new TypeError("argument should be a Buffer");
      if (w || (w = 0), !T && T !== 0 && (T = this.length), d >= u.length && (d = u.length), d || (d = 0), T > 0 && T < w && (T = w), T === w || u.length === 0 || this.length === 0) return 0;
      if (d < 0) throw new RangeError("targetStart out of bounds");
      if (w < 0 || w >= this.length) throw new RangeError("Index out of range");
      if (T < 0) throw new RangeError("sourceEnd out of bounds");
      T > this.length && (T = this.length), u.length - d < T - w && (T = u.length - d + w);
      const P = T - w;
      return this === u && typeof Uint8Array.prototype.copyWithin == "function" ? this.copyWithin(d, w, T) : Uint8Array.prototype.set.call(u, this.subarray(w, T), d), P;
    }, a.prototype.fill = function(u, d, w, T) {
      if (typeof u == "string") {
        if (typeof d == "string" ? (T = d, d = 0, w = this.length) : typeof w == "string" && (T = w, w = this.length), T !== void 0 && typeof T != "string") throw new TypeError("encoding must be a string");
        if (typeof T == "string" && !a.isEncoding(T)) throw new TypeError("Unknown encoding: " + T);
        if (u.length === 1) {
          const G = u.charCodeAt(0);
          (T === "utf8" && G < 128 || T === "latin1") && (u = G);
        }
      } else typeof u == "number" ? u = u & 255 : typeof u == "boolean" && (u = Number(u));
      if (d < 0 || this.length < d || this.length < w) throw new RangeError("Out of range index");
      if (w <= d) return this;
      d = d >>> 0, w = w === void 0 ? this.length : w >>> 0, u || (u = 0);
      let P;
      if (typeof u == "number") for (P = d; P < w; ++P) this[P] = u;
      else {
        const G = a.isBuffer(u) ? u : a.from(u, T), fe = G.length;
        if (fe === 0) throw new TypeError('The value "' + u + '" is invalid for argument "value"');
        for (P = 0; P < w - d; ++P) this[P + d] = G[P % fe];
      }
      return this;
    };
    const Z = {};
    function Qe(g, u, d) {
      Z[g] = class extends d {
        constructor() {
          super(), Object.defineProperty(this, "message", {
            value: u.apply(this, arguments),
            writable: true,
            configurable: true
          }), this.name = `${this.name} [${g}]`, this.stack, delete this.name;
        }
        get code() {
          return g;
        }
        set code(T) {
          Object.defineProperty(this, "code", {
            configurable: true,
            enumerable: true,
            value: T,
            writable: true
          });
        }
        toString() {
          return `${this.name} [${g}]: ${this.message}`;
        }
      };
    }
    Qe("ERR_BUFFER_OUT_OF_BOUNDS", function(g) {
      return g ? `${g} is outside of buffer bounds` : "Attempt to access memory outside buffer bounds";
    }, RangeError), Qe("ERR_INVALID_ARG_TYPE", function(g, u) {
      return `The "${g}" argument must be of type number. Received type ${typeof u}`;
    }, TypeError), Qe("ERR_OUT_OF_RANGE", function(g, u, d) {
      let w = `The value of "${g}" is out of range.`, T = d;
      return Number.isInteger(d) && Math.abs(d) > 2 ** 32 ? T = ze(String(d)) : typeof d == "bigint" && (T = String(d), (d > BigInt(2) ** BigInt(32) || d < -(BigInt(2) ** BigInt(32))) && (T = ze(T)), T += "n"), w += ` It must be ${u}. Received ${T}`, w;
    }, RangeError);
    function ze(g) {
      let u = "", d = g.length;
      const w = g[0] === "-" ? 1 : 0;
      for (; d >= w + 4; d -= 3) u = `_${g.slice(d - 3, d)}${u}`;
      return `${g.slice(0, d)}${u}`;
    }
    function _n(g, u, d) {
      mt(u, "offset"), (g[u] === void 0 || g[u + d] === void 0) && Xe(u, g.length - (d + 1));
    }
    function st(g, u, d, w, T, P) {
      if (g > d || g < u) {
        const G = typeof u == "bigint" ? "n" : "";
        let fe;
        throw u === 0 || u === BigInt(0) ? fe = `>= 0${G} and < 2${G} ** ${(P + 1) * 8}${G}` : fe = `>= -(2${G} ** ${(P + 1) * 8 - 1}${G}) and < 2 ** ${(P + 1) * 8 - 1}${G}`, new Z.ERR_OUT_OF_RANGE("value", fe, g);
      }
      _n(w, T, P);
    }
    function mt(g, u) {
      if (typeof g != "number") throw new Z.ERR_INVALID_ARG_TYPE(u, "number", g);
    }
    function Xe(g, u, d) {
      throw Math.floor(g) !== g ? (mt(g, d), new Z.ERR_OUT_OF_RANGE("offset", "an integer", g)) : u < 0 ? new Z.ERR_BUFFER_OUT_OF_BOUNDS() : new Z.ERR_OUT_OF_RANGE("offset", `>= 0 and <= ${u}`, g);
    }
    const me = /[^+/0-9A-Za-z-_]/g;
    function ve(g) {
      if (g = g.split("=")[0], g = g.trim().replace(me, ""), g.length < 2) return "";
      for (; g.length % 4 !== 0; ) g = g + "=";
      return g;
    }
    function he(g, u) {
      u = u || 1 / 0;
      let d;
      const w = g.length;
      let T = null;
      const P = [];
      for (let G = 0; G < w; ++G) {
        if (d = g.charCodeAt(G), d > 55295 && d < 57344) {
          if (!T) {
            if (d > 56319) {
              (u -= 3) > -1 && P.push(239, 191, 189);
              continue;
            } else if (G + 1 === w) {
              (u -= 3) > -1 && P.push(239, 191, 189);
              continue;
            }
            T = d;
            continue;
          }
          if (d < 56320) {
            (u -= 3) > -1 && P.push(239, 191, 189), T = d;
            continue;
          }
          d = (T - 55296 << 10 | d - 56320) + 65536;
        } else T && (u -= 3) > -1 && P.push(239, 191, 189);
        if (T = null, d < 128) {
          if ((u -= 1) < 0) break;
          P.push(d);
        } else if (d < 2048) {
          if ((u -= 2) < 0) break;
          P.push(d >> 6 | 192, d & 63 | 128);
        } else if (d < 65536) {
          if ((u -= 3) < 0) break;
          P.push(d >> 12 | 224, d >> 6 & 63 | 128, d & 63 | 128);
        } else if (d < 1114112) {
          if ((u -= 4) < 0) break;
          P.push(d >> 18 | 240, d >> 12 & 63 | 128, d >> 6 & 63 | 128, d & 63 | 128);
        } else throw new Error("Invalid code point");
      }
      return P;
    }
    function vt(g) {
      const u = [];
      for (let d = 0; d < g.length; ++d) u.push(g.charCodeAt(d) & 255);
      return u;
    }
    function le(g, u) {
      let d, w, T;
      const P = [];
      for (let G = 0; G < g.length && !((u -= 2) < 0); ++G) d = g.charCodeAt(G), w = d >> 8, T = d % 256, P.push(T), P.push(w);
      return P;
    }
    function se(g) {
      return t.toByteArray(ve(g));
    }
    function U(g, u, d, w) {
      let T;
      for (T = 0; T < w && !(T + d >= u.length || T >= g.length); ++T) u[T + d] = g[T];
      return T;
    }
    function He(g, u) {
      return g instanceof u || g != null && g.constructor != null && g.constructor.name != null && g.constructor.name === u.name;
    }
    function Pt(g) {
      return g !== g;
    }
    const ln = function() {
      const g = "0123456789abcdef", u = new Array(256);
      for (let d = 0; d < 16; ++d) {
        const w = d * 16;
        for (let T = 0; T < 16; ++T) u[w + T] = g[d] + g[T];
      }
      return u;
    }();
    function at(g) {
      return typeof BigInt > "u" ? yt : g;
    }
    function yt() {
      throw new Error("BigInt not supported");
    }
  })(Up);
  const t0 = "modulepreload", n0 = function(e) {
    return "/" + e;
  }, Pd = {}, r0 = function(t, n, r) {
    let i = Promise.resolve();
    if (n && n.length > 0) {
      document.getElementsByTagName("link");
      const s = document.querySelector("meta[property=csp-nonce]"), a = (s == null ? void 0 : s.nonce) || (s == null ? void 0 : s.getAttribute("nonce"));
      i = Promise.allSettled(n.map((l) => {
        if (l = n0(l), l in Pd) return;
        Pd[l] = true;
        const c = l.endsWith(".css"), h = c ? '[rel="stylesheet"]' : "";
        if (document.querySelector(`link[href="${l}"]${h}`)) return;
        const f = document.createElement("link");
        if (f.rel = c ? "stylesheet" : t0, c || (f.as = "script"), f.crossOrigin = "", f.href = l, a && f.setAttribute("nonce", a), document.head.appendChild(f), c) return new Promise((p, y) => {
          f.addEventListener("load", p), f.addEventListener("error", () => y(new Error(`Unable to preload CSS for ${l}`)));
        });
      }));
    }
    function o(s) {
      const a = new Event("vite:preloadError", {
        cancelable: true
      });
      if (a.payload = s, window.dispatchEvent(a), !a.defaultPrevented) throw s;
    }
    return i.then((s) => {
      for (const a of s || []) a.status === "rejected" && o(a.reason);
      return t().catch(o);
    });
  };
  const Mp = Symbol("Comlink.proxy"), i0 = Symbol("Comlink.endpoint"), o0 = Symbol("Comlink.releaseProxy"), Ja = Symbol("Comlink.finalizer"), Ss = Symbol("Comlink.thrown"), $p = (e) => typeof e == "object" && e !== null || typeof e == "function", s0 = {
    canHandle: (e) => $p(e) && e[Mp],
    serialize(e) {
      const { port1: t, port2: n } = new MessageChannel();
      return Hp(e, t), [
        n,
        [
          n
        ]
      ];
    },
    deserialize(e) {
      return e.start(), Vp(e);
    }
  }, a0 = {
    canHandle: (e) => $p(e) && Ss in e,
    serialize({ value: e }) {
      let t;
      return e instanceof Error ? t = {
        isError: true,
        value: {
          message: e.message,
          name: e.name,
          stack: e.stack
        }
      } : t = {
        isError: false,
        value: e
      }, [
        t,
        []
      ];
    },
    deserialize(e) {
      throw e.isError ? Object.assign(new Error(e.value.message), e.value) : e.value;
    }
  }, jp = /* @__PURE__ */ new Map([
    [
      "proxy",
      s0
    ],
    [
      "throw",
      a0
    ]
  ]);
  function l0(e, t) {
    for (const n of e) if (t === n || n === "*" || n instanceof RegExp && n.test(t)) return true;
    return false;
  }
  function Hp(e, t = globalThis, n = [
    "*"
  ]) {
    t.addEventListener("message", function r(i) {
      if (!i || !i.data) return;
      if (!l0(n, i.origin)) {
        console.warn(`Invalid origin '${i.origin}' for comlink proxy`);
        return;
      }
      const { id: o, type: s, path: a } = Object.assign({
        path: []
      }, i.data), l = (i.data.argumentList || []).map(Cr);
      let c;
      try {
        const h = a.slice(0, -1).reduce((p, y) => p[y], e), f = a.reduce((p, y) => p[y], e);
        switch (s) {
          case "GET":
            c = f;
            break;
          case "SET":
            h[a.slice(-1)[0]] = Cr(i.data.value), c = true;
            break;
          case "APPLY":
            c = f.apply(h, l);
            break;
          case "CONSTRUCT":
            {
              const p = new f(...l);
              c = Zi(p);
            }
            break;
          case "ENDPOINT":
            {
              const { port1: p, port2: y } = new MessageChannel();
              Hp(e, y), c = h0(p, [
                p
              ]);
            }
            break;
          case "RELEASE":
            c = void 0;
            break;
          default:
            return;
        }
      } catch (h) {
        c = {
          value: h,
          [Ss]: 0
        };
      }
      Promise.resolve(c).catch((h) => ({
        value: h,
        [Ss]: 0
      })).then((h) => {
        const [f, p] = Xs(h);
        t.postMessage(Object.assign(Object.assign({}, f), {
          id: o
        }), p), s === "RELEASE" && (t.removeEventListener("message", r), Wp(t), Ja in e && typeof e[Ja] == "function" && e[Ja]());
      }).catch((h) => {
        const [f, p] = Xs({
          value: new TypeError("Unserializable return value"),
          [Ss]: 0
        });
        t.postMessage(Object.assign(Object.assign({}, f), {
          id: o
        }), p);
      });
    }), t.start && t.start();
  }
  function u0(e) {
    return e.constructor.name === "MessagePort";
  }
  function Wp(e) {
    u0(e) && e.close();
  }
  function Vp(e, t) {
    const n = /* @__PURE__ */ new Map();
    return e.addEventListener("message", function(i) {
      const { data: o } = i;
      if (!o || !o.id) return;
      const s = n.get(o.id);
      if (s) try {
        s(o);
      } finally {
        n.delete(o.id);
      }
    }), au(e, n, [], t);
  }
  function es(e) {
    if (e) throw new Error("Proxy has been released and is not useable");
  }
  function Kp(e) {
    return $r(e, /* @__PURE__ */ new Map(), {
      type: "RELEASE"
    }).then(() => {
      Wp(e);
    });
  }
  const Ys = /* @__PURE__ */ new WeakMap(), Qs = "FinalizationRegistry" in globalThis && new FinalizationRegistry((e) => {
    const t = (Ys.get(e) || 0) - 1;
    Ys.set(e, t), t === 0 && Kp(e);
  });
  function c0(e, t) {
    const n = (Ys.get(t) || 0) + 1;
    Ys.set(t, n), Qs && Qs.register(e, t, e);
  }
  function d0(e) {
    Qs && Qs.unregister(e);
  }
  function au(e, t, n = [], r = function() {
  }) {
    let i = false;
    const o = new Proxy(r, {
      get(s, a) {
        if (es(i), a === o0) return () => {
          d0(o), Kp(e), t.clear(), i = true;
        };
        if (a === "then") {
          if (n.length === 0) return {
            then: () => o
          };
          const l = $r(e, t, {
            type: "GET",
            path: n.map((c) => c.toString())
          }).then(Cr);
          return l.then.bind(l);
        }
        return au(e, t, [
          ...n,
          a
        ]);
      },
      set(s, a, l) {
        es(i);
        const [c, h] = Xs(l);
        return $r(e, t, {
          type: "SET",
          path: [
            ...n,
            a
          ].map((f) => f.toString()),
          value: c
        }, h).then(Cr);
      },
      apply(s, a, l) {
        es(i);
        const c = n[n.length - 1];
        if (c === i0) return $r(e, t, {
          type: "ENDPOINT"
        }).then(Cr);
        if (c === "bind") return au(e, t, n.slice(0, -1));
        const [h, f] = Nd(l);
        return $r(e, t, {
          type: "APPLY",
          path: n.map((p) => p.toString()),
          argumentList: h
        }, f).then(Cr);
      },
      construct(s, a) {
        es(i);
        const [l, c] = Nd(a);
        return $r(e, t, {
          type: "CONSTRUCT",
          path: n.map((h) => h.toString()),
          argumentList: l
        }, c).then(Cr);
      }
    });
    return c0(o, e), o;
  }
  function f0(e) {
    return Array.prototype.concat.apply([], e);
  }
  function Nd(e) {
    const t = e.map(Xs);
    return [
      t.map((n) => n[0]),
      f0(t.map((n) => n[1]))
    ];
  }
  const Yp = /* @__PURE__ */ new WeakMap();
  function h0(e, t) {
    return Yp.set(e, t), e;
  }
  function Zi(e) {
    return Object.assign(e, {
      [Mp]: true
    });
  }
  function Xs(e) {
    for (const [t, n] of jp) if (n.canHandle(e)) {
      const [r, i] = n.serialize(e);
      return [
        {
          type: "HANDLER",
          name: t,
          value: r
        },
        i
      ];
    }
    return [
      {
        type: "RAW",
        value: e
      },
      Yp.get(e) || []
    ];
  }
  function Cr(e) {
    switch (e.type) {
      case "HANDLER":
        return jp.get(e.name).deserialize(e.value);
      case "RAW":
        return e.value;
    }
  }
  function $r(e, t, n, r) {
    return new Promise((i) => {
      const o = p0();
      t.set(o, i), e.start && e.start(), e.postMessage(Object.assign({
        id: o
      }, n), r);
    });
  }
  function p0() {
    return new Array(4).fill(0).map(() => Math.floor(Math.random() * Number.MAX_SAFE_INTEGER).toString(16)).join("-");
  }
  const Fd = (e, t) => {
    const n = t();
    return e.nodes.forEach((r) => n.addNode(r)), e.relationships.forEach((r) => n.addRelationship(r)), {
      graph: n,
      fileContents: new Map(Object.entries(e.fileContents))
    };
  }, el = () => {
    const e = /* @__PURE__ */ new Map(), t = /* @__PURE__ */ new Map();
    return {
      get nodes() {
        return Array.from(e.values());
      },
      get relationships() {
        return Array.from(t.values());
      },
      get nodeCount() {
        return e.size;
      },
      get relationshipCount() {
        return t.size;
      },
      addNode: (i) => {
        e.has(i.id) || e.set(i.id, i);
      },
      addRelationship: (i) => {
        t.has(i.id) || t.set(i.id, i);
      }
    };
  }, zd = {
    Project: "#a855f7",
    Package: "#8b5cf6",
    Module: "#7c3aed",
    Folder: "#6366f1",
    File: "#3b82f6",
    Class: "#f59e0b",
    Function: "#10b981",
    Method: "#14b8a6",
    Variable: "#64748b",
    Interface: "#ec4899",
    Enum: "#f97316",
    Decorator: "#eab308",
    Import: "#475569",
    Type: "#a78bfa",
    CodeElement: "#64748b",
    Community: "#818cf8",
    Process: "#f43f5e"
  }, Od = {
    Project: 20,
    Package: 16,
    Module: 13,
    Folder: 10,
    File: 6,
    Class: 8,
    Function: 4,
    Method: 3,
    Variable: 2,
    Interface: 7,
    Enum: 5,
    Decorator: 2,
    Import: 1.5,
    Type: 3,
    CodeElement: 2,
    Community: 0,
    Process: 0
  }, Gd = [
    "#ef4444",
    "#f97316",
    "#eab308",
    "#22c55e",
    "#06b6d4",
    "#3b82f6",
    "#8b5cf6",
    "#d946ef",
    "#ec4899",
    "#f43f5e",
    "#14b8a6",
    "#84cc16"
  ], Ud = (e) => Gd[e % Gd.length], g0 = [
    "Project",
    "Package",
    "Module",
    "Folder",
    "File",
    "Class",
    "Function",
    "Method",
    "Interface",
    "Enum",
    "Type"
  ], m0 = [
    "CONTAINS",
    "DEFINES",
    "IMPORTS",
    "EXTENDS",
    "IMPLEMENTS",
    "CALLS"
  ], Pn = {
    activeProvider: "gemini",
    intelligentClustering: false,
    hasSeenClusteringPrompt: false,
    useSameModelForClustering: true,
    openai: {
      apiKey: "",
      model: "gpt-4o",
      temperature: 0.1
    },
    gemini: {
      apiKey: "",
      model: "gemini-2.0-flash",
      temperature: 0.1
    },
    azureOpenAI: {
      apiKey: "",
      endpoint: "",
      deploymentName: "",
      model: "gpt-4o",
      apiVersion: "2024-08-01-preview",
      temperature: 0.1
    },
    anthropic: {
      apiKey: "",
      model: "claude-sonnet-4-20250514",
      temperature: 0.1
    },
    ollama: {
      baseUrl: "http://localhost:11434",
      model: "llama3.2",
      temperature: 0.1
    },
    openrouter: {
      apiKey: "",
      model: "",
      baseUrl: "https://openrouter.ai/api/v1",
      temperature: 0.1
    }
  }, Qp = "gitnexus-llm-settings", lu = () => {
    try {
      const e = localStorage.getItem(Qp);
      if (!e) return Pn;
      const t = JSON.parse(e);
      return {
        ...Pn,
        ...t,
        openai: {
          ...Pn.openai,
          ...t.openai
        },
        azureOpenAI: {
          ...Pn.azureOpenAI,
          ...t.azureOpenAI
        },
        gemini: {
          ...Pn.gemini,
          ...t.gemini
        },
        anthropic: {
          ...Pn.anthropic,
          ...t.anthropic
        },
        ollama: {
          ...Pn.ollama,
          ...t.ollama
        },
        openrouter: {
          ...Pn.openrouter,
          ...t.openrouter
        }
      };
    } catch (e) {
      return console.warn("Failed to load LLM settings:", e), Pn;
    }
  }, v0 = (e) => {
    try {
      localStorage.setItem(Qp, JSON.stringify(e));
    } catch (t) {
      console.error("Failed to save LLM settings:", t);
    }
  }, Zs = () => {
    var _a2, _b, _c, _d2, _e, _f2;
    const e = lu();
    switch (e.activeProvider) {
      case "openai":
        return ((_a2 = e.openai) == null ? void 0 : _a2.apiKey) ? {
          provider: "openai",
          ...e.openai
        } : null;
      case "azure-openai":
        return !((_b = e.azureOpenAI) == null ? void 0 : _b.apiKey) || !((_c = e.azureOpenAI) == null ? void 0 : _c.endpoint) ? null : {
          provider: "azure-openai",
          ...e.azureOpenAI
        };
      case "gemini":
        return ((_d2 = e.gemini) == null ? void 0 : _d2.apiKey) ? {
          provider: "gemini",
          ...e.gemini
        } : null;
      case "anthropic":
        return ((_e = e.anthropic) == null ? void 0 : _e.apiKey) ? {
          provider: "anthropic",
          ...e.anthropic
        } : null;
      case "ollama":
        return {
          provider: "ollama",
          ...e.ollama
        };
      case "openrouter":
        return !((_f2 = e.openrouter) == null ? void 0 : _f2.apiKey) || e.openrouter.apiKey.trim() === "" ? null : {
          provider: "openrouter",
          apiKey: e.openrouter.apiKey,
          model: e.openrouter.model || "",
          baseUrl: e.openrouter.baseUrl || "https://openrouter.ai/api/v1",
          temperature: e.openrouter.temperature,
          maxTokens: e.openrouter.maxTokens
        };
      default:
        return null;
    }
  };
  function y0(e) {
    let t = e.trim();
    return t = t.replace(/\/+$/, ""), !t.startsWith("http://") && !t.startsWith("https://") && (t.startsWith("localhost") || t.startsWith("127.0.0.1") ? t = `http://${t}` : t = `https://${t}`), t.endsWith("/api") || (t = `${t}/api`), t;
  }
  async function w0(e, t) {
    const n = t ? `${e}/repo?repo=${encodeURIComponent(t)}` : `${e}/repo`, r = await fetch(n);
    if (!r.ok) throw new Error(`Server returned ${r.status}: ${r.statusText}`);
    const i = await r.json();
    return {
      ...i,
      repoPath: i.repoPath ?? i.path
    };
  }
  async function E0(e, t, n, r) {
    const i = r ? `${e}/graph?repo=${encodeURIComponent(r)}` : `${e}/graph`, o = await fetch(i, {
      signal: n
    });
    if (!o.ok) throw new Error(`Server returned ${o.status}: ${o.statusText}`);
    const s = o.headers.get("Content-Length"), a = s ? parseInt(s, 10) : null;
    if (!o.body) return await o.json();
    const l = o.body.getReader(), c = [];
    let h = 0;
    for (; ; ) {
      const { done: k, value: b } = await l.read();
      if (k) break;
      c.push(b), h += b.length, t == null ? void 0 : t(h, a);
    }
    const f = new Uint8Array(h);
    let p = 0;
    for (const k of c) f.set(k, p), p += k.length;
    const y = new TextDecoder().decode(f);
    return JSON.parse(y);
  }
  function S0(e) {
    const t = {};
    for (const n of e) n.label === "File" && n.properties.content && (t[n.properties.filePath] = n.properties.content);
    return t;
  }
  async function _0(e, t, n, r) {
    const i = y0(e);
    t == null ? void 0 : t("validating", 0, null);
    const o = await w0(i, r);
    t == null ? void 0 : t("downloading", 0, null);
    const { nodes: s, relationships: a } = await E0(i, (c, h) => t == null ? void 0 : t("downloading", c, h), n, r);
    t == null ? void 0 : t("extracting", 0, null);
    const l = S0(s);
    return {
      nodes: s,
      relationships: a,
      fileContents: l,
      repoInfo: o
    };
  }
  const Xp = z.createContext(null), k0 = ({ children: e }) => {
    const [t, n] = z.useState("onboarding"), [r, i] = z.useState(null), [o, s] = z.useState(/* @__PURE__ */ new Map()), [a, l] = z.useState(null), [c, h] = z.useState(false), [f, p] = z.useState("code"), y = z.useCallback(() => {
      xe(true);
    }, []), k = z.useCallback(() => {
      h(true), p("chat");
    }, []), [b, I] = z.useState(g0), [_, m] = z.useState(m0), [v, E] = z.useState(null), [A, F] = z.useState(/* @__PURE__ */ new Set()), [R, L] = z.useState(null), [C, N] = z.useState(/* @__PURE__ */ new Set()), [V, B] = z.useState(/* @__PURE__ */ new Set()), [K, O] = z.useState(/* @__PURE__ */ new Set()), [re, ae] = z.useState(true), J = z.useCallback(() => {
      ae((q) => !q);
    }, []), S = z.useCallback(() => {
      B(/* @__PURE__ */ new Set());
    }, []), j = z.useCallback(() => {
      O(/* @__PURE__ */ new Set());
    }, []), H = z.useCallback(() => {
      F(/* @__PURE__ */ new Set()), L(null);
    }, []), [D, x] = z.useState(/* @__PURE__ */ new Map()), Q = z.useRef(null), ie = z.useCallback((q, ne) => {
      const de = Date.now(), pe = ne === "pulse" ? 2e3 : ne === "ripple" ? 3e3 : 4e3;
      x((ge) => {
        const ue = new Map(ge);
        for (const ye of q) ue.set(ye, {
          type: ne,
          startTime: de,
          duration: pe
        });
        return ue;
      }), setTimeout(() => {
        x((ge) => {
          const ue = new Map(ge);
          for (const ye of q) {
            const $t = ue.get(ye);
            $t && $t.startTime === de && ue.delete(ye);
          }
          return ue;
        });
      }, pe + 100);
    }, []), _e = z.useCallback(() => {
      x(/* @__PURE__ */ new Map()), Q.current && (clearInterval(Q.current), Q.current = null);
    }, []), [Se, oe] = z.useState(null), [Z, Qe] = z.useState(""), [ze, _n] = z.useState(null), [st, mt] = z.useState([]), [Xe, me] = z.useState("idle"), [ve, he] = z.useState(null), [vt, le] = z.useState(lu), [se, U] = z.useState(false), [He, Pt] = z.useState(false), [ln, at] = z.useState(false), [yt, g] = z.useState(null), [u, d] = z.useState([]), [w, T] = z.useState(false), [P, G] = z.useState([]), [fe, ke] = z.useState([]), [Ce, xe] = z.useState(false), [Le, No] = z.useState(null), Zn = z.useCallback((q) => q.replace(/\\/g, "/").replace(/^\.?\//, ""), []), ba = z.useCallback((q) => {
      const ne = Zn(q).toLowerCase();
      if (!ne) return null;
      for (const ge of o.keys()) if (Zn(ge).toLowerCase() === ne) return ge;
      let de = null;
      for (const ge of o.keys()) {
        const ue = Zn(ge).toLowerCase();
        if (ue.endsWith(ne)) {
          const ye = 1e3 - ue.length;
          (!de || ye > de.score) && (de = {
            path: ge,
            score: ye
          });
        }
      }
      if (de) return de.path;
      const pe = ne.split("/").filter(Boolean);
      for (const ge of o.keys()) {
        const ue = Zn(ge).toLowerCase().split("/").filter(Boolean);
        let ye = 0;
        for (const $t of pe) {
          const un = ue.findIndex((lt, We) => We >= ye && lt.includes($t));
          if (un === -1) {
            ye = -1;
            break;
          }
          ye = un + 1;
        }
        if (ye !== -1) return ge;
      }
      return null;
    }, [
      o,
      Zn
    ]), _c = z.useCallback((q) => {
      var _a2;
      if (!r) return;
      const ne = Zn(q);
      return (_a2 = r.nodes.find((pe) => pe.label === "File" && Zn(pe.properties.filePath) === ne)) == null ? void 0 : _a2.id;
    }, [
      r,
      Zn
    ]), Fo = z.useCallback((q) => {
      const ne = `ref-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, de = {
        ...q,
        id: ne
      };
      ke((pe) => pe.some((ue) => ue.filePath === q.filePath && ue.startLine === q.startLine && ue.endLine === q.endLine) ? pe : [
        ...pe,
        de
      ]), xe(true), No({
        filePath: q.filePath,
        startLine: q.startLine,
        endLine: q.endLine,
        ts: Date.now()
      }), q.nodeId && q.source === "ai" && N((pe) => /* @__PURE__ */ new Set([
        ...pe,
        q.nodeId
      ]));
    }, []), xa = z.useCallback(() => {
      ke((q) => {
        const ne = q.filter((ge) => ge.source === "ai"), de = q.filter((ge) => ge.source !== "ai"), pe = new Set(ne.map((ge) => ge.nodeId).filter(Boolean));
        return pe.size > 0 && N((ge) => {
          const ue = new Set(ge);
          for (const ye of pe) ue.delete(ye);
          return ue;
        }), de.length === 0 && !a && xe(false), de;
      });
    }, [
      R,
      a
    ]);
    z.useEffect(() => {
      a && xe(true);
    }, [
      a
    ]);
    const kc = z.useRef(null), Nt = z.useRef(null);
    z.useEffect(() => {
      const q = new Worker(new URL("/assets/ingestion.worker-BiTDjgSE.js", import.meta.url), {
        type: "module"
      }), ne = Vp(q);
      return kc.current = q, Nt.current = ne, () => {
        q.terminate(), kc.current = null, Nt.current = null;
      };
    }, []);
    const em = z.useCallback(async (q, ne, de) => {
      const pe = Nt.current;
      if (!pe) throw new Error("Worker not initialized");
      const ge = Zi(ne), ue = await pe.runPipeline(q, ge, de);
      return Fd(ue, el);
    }, []), tm = z.useCallback(async (q, ne, de) => {
      const pe = Nt.current;
      if (!pe) throw new Error("Worker not initialized");
      const ge = Zi(ne), ue = await pe.runPipelineFromFiles(q, ge, de);
      return Fd(ue, el);
    }, []), nm = z.useCallback(async (q) => {
      const ne = Nt.current;
      if (!ne) throw new Error("Worker not initialized");
      return ne.runQuery(q);
    }, []), rm = z.useCallback(async () => {
      const q = Nt.current;
      if (!q) return false;
      try {
        return await q.isReady();
      } catch {
        return false;
      }
    }, []), zo = z.useCallback(async (q) => {
      var _a2;
      const ne = Nt.current;
      if (!ne) throw new Error("Worker not initialized");
      me("loading"), he(null);
      try {
        const de = Zi((pe) => {
          switch (he(pe), pe.phase) {
            case "loading-model":
              me("loading");
              break;
            case "embedding":
              me("embedding");
              break;
            case "indexing":
              me("indexing");
              break;
            case "ready":
              me("ready");
              break;
            case "error":
              me("error");
              break;
          }
        });
        await ne.startEmbeddingPipeline(de, q);
      } catch (de) {
        throw (de == null ? void 0 : de.name) === "WebGPUNotAvailableError" || ((_a2 = de == null ? void 0 : de.message) == null ? void 0 : _a2.includes("WebGPU not available")) ? me("idle") : me("error"), de;
      }
    }, []), im = z.useCallback(async (q, ne = 10) => {
      const de = Nt.current;
      if (!de) throw new Error("Worker not initialized");
      return de.semanticSearch(q, ne);
    }, []), om = z.useCallback(async (q, ne = 5, de = 2) => {
      const pe = Nt.current;
      if (!pe) throw new Error("Worker not initialized");
      return pe.semanticSearchWithContext(q, ne, de);
    }, []), sm = z.useCallback(async () => {
      const q = Nt.current;
      return q ? q.testArrayParams() : {
        success: false,
        error: "Worker not initialized"
      };
    }, []), am = z.useCallback((q) => {
      le((ne) => {
        const de = {
          ...ne,
          ...q
        };
        return v0(de), de;
      });
    }, []), lm = z.useCallback(() => {
      le(lu());
    }, []), Ti = z.useCallback(async (q) => {
      const ne = Nt.current;
      if (!ne) {
        g("Worker not initialized");
        return;
      }
      const de = Zs();
      if (!de) {
        g("Please configure an LLM provider in settings");
        return;
      }
      at(true), g(null);
      try {
        const pe = q || Z || "project", ge = await ne.initializeAgent(de, pe);
        ge.success ? (Pt(true), g(null)) : (g(ge.error ?? "Failed to initialize agent"), Pt(false));
      } catch (pe) {
        const ge = pe instanceof Error ? pe.message : String(pe);
        g(ge), Pt(false);
      } finally {
        at(false);
      }
    }, [
      Z
    ]), um = z.useCallback(async (q) => {
      const ne = Nt.current;
      if (!ne) {
        g("Worker not initialized");
        return;
      }
      if (xa(), S(), !He && (await Ti(), !Nt.current)) return;
      const de = {
        id: `user-${Date.now()}`,
        role: "user",
        content: q,
        timestamp: Date.now()
      };
      if (d((lt) => [
        ...lt,
        de
      ]), Xe === "indexing") {
        const lt = {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: "Wait a moment, vector index is being created.",
          timestamp: Date.now()
        };
        d((We) => [
          ...We,
          lt
        ]), g(null), T(false), G([]);
        return;
      }
      T(true), G([]);
      const pe = [
        ...u,
        de
      ].map((lt) => ({
        role: lt.role === "tool" ? "assistant" : lt.role,
        content: lt.content
      })), ge = `assistant-${Date.now()}`, ue = [], ye = [];
      let $t = 0;
      const un = () => {
        const We = ue.filter((we) => we.type === "reasoning" || we.type === "content").map((we) => we.content).filter(Boolean).join(`

`);
        d((we) => {
          const wt = we.find((Ie) => Ie.id === ge), cn = {
            id: ge,
            role: "assistant",
            content: We,
            steps: [
              ...ue
            ],
            toolCalls: [
              ...ye
            ],
            timestamp: (wt == null ? void 0 : wt.timestamp) ?? Date.now()
          };
          return wt ? we.map((Ie) => Ie.id === ge ? cn : Ie) : [
            ...we,
            cn
          ];
        });
      };
      try {
        const lt = Zi((We) => {
          switch (We.type) {
            case "reasoning":
              if (We.reasoning) {
                const we = ue[ue.length - 1];
                we && we.type === "reasoning" ? ue[ue.length - 1] = {
                  ...we,
                  content: (we.content || "") + We.reasoning
                } : ue.push({
                  id: `step-${$t++}`,
                  type: "reasoning",
                  content: We.reasoning
                }), un();
              }
              break;
            case "content":
              if (We.content) {
                const we = ue[ue.length - 1];
                we && we.type === "content" ? ue[ue.length - 1] = {
                  ...we,
                  content: (we.content || "") + We.content
                } : ue.push({
                  id: `step-${$t++}`,
                  type: "content",
                  content: We.content
                }), un();
                const wt = ue[ue.length - 1], cn = wt && wt.type === "content" && wt.content || "", Ie = /\[\[([a-zA-Z0-9_\-./\\]+\.[a-zA-Z0-9]+)(?::(\d+)(?:[-–](\d+))?)?\]\]/g;
                let Et;
                for (; (Et = Ie.exec(cn)) !== null; ) {
                  const Dn = Et[1].trim(), tt = Et[2] ? parseInt(Et[2], 10) : void 0, nt = Et[3] ? parseInt(Et[3], 10) : tt, Ft = ba(Dn);
                  if (!Ft) continue;
                  const Ri = tt !== void 0 ? Math.max(0, tt - 1) : void 0, ym = nt !== void 0 ? Math.max(0, nt - 1) : Ri, wm = _c(Ft);
                  Fo({
                    filePath: Ft,
                    startLine: Ri,
                    endLine: ym,
                    nodeId: wm,
                    label: "File",
                    name: Ft.split("/").pop() ?? Ft,
                    source: "ai"
                  });
                }
                const Ve = /\[\[(?:graph:)?(Class|Function|Method|Interface|File|Folder|Variable|Enum|Type|CodeElement):([^\]]+)\]\]/g;
                let et;
                for (; (et = Ve.exec(cn)) !== null; ) {
                  const Dn = et[1], tt = et[2].trim();
                  if (!r) continue;
                  const nt = r.nodes.find((Ri) => Ri.label === Dn && Ri.properties.name === tt);
                  if (!nt || !nt.properties.filePath) continue;
                  const Ft = ba(nt.properties.filePath);
                  Ft && Fo({
                    filePath: Ft,
                    startLine: nt.properties.startLine ? nt.properties.startLine - 1 : void 0,
                    endLine: nt.properties.endLine ? nt.properties.endLine - 1 : void 0,
                    nodeId: nt.id,
                    label: nt.label,
                    name: nt.properties.name,
                    source: "ai"
                  });
                }
              }
              break;
            case "tool_call":
              if (We.toolCall) {
                const we = We.toolCall;
                ye.push(we), ue.push({
                  id: `step-${$t++}`,
                  type: "tool_call",
                  toolCall: we
                }), G((wt) => [
                  ...wt,
                  we
                ]), un();
              }
              break;
            case "tool_result":
              if (We.toolCall) {
                const we = We.toolCall;
                let wt = ye.findIndex((Ie) => Ie.id === we.id);
                wt < 0 && (wt = ye.findIndex((Ie) => Ie.name === we.name && Ie.status === "running")), wt < 0 && (wt = ye.findIndex((Ie) => Ie.name === we.name && !Ie.result)), wt >= 0 && (ye[wt] = {
                  ...ye[wt],
                  result: we.result,
                  status: "completed"
                });
                const cn = ue.findIndex((Ie) => Ie.type === "tool_call" && Ie.toolCall && (Ie.toolCall.id === we.id || Ie.toolCall.name === we.name && Ie.toolCall.status === "running"));
                if (cn >= 0 && ue[cn].toolCall && (ue[cn] = {
                  ...ue[cn],
                  toolCall: {
                    ...ue[cn].toolCall,
                    result: we.result,
                    status: "completed"
                  }
                }), G((Ie) => {
                  let Et = Ie.findIndex((Ve) => Ve.id === we.id);
                  return Et < 0 && (Et = Ie.findIndex((Ve) => Ve.name === we.name && Ve.status === "running")), Et < 0 && (Et = Ie.findIndex((Ve) => Ve.name === we.name && !Ve.result)), Et >= 0 ? Ie.map((Ve, et) => et === Et ? {
                    ...Ve,
                    result: we.result,
                    status: "completed"
                  } : Ve) : Ie;
                }), un(), we.result) {
                  const Ie = we.result.match(/\[HIGHLIGHT_NODES:([^\]]+)\]/);
                  if (Ie) {
                    const Ve = Ie[1].split(",").map((et) => et.trim()).filter(Boolean);
                    if (Ve.length > 0 && r) {
                      const et = /* @__PURE__ */ new Set(), Dn = r.nodes.map((tt) => tt.id);
                      for (const tt of Ve) if (Dn.includes(tt)) et.add(tt);
                      else {
                        const nt = Dn.find((Ft) => Ft.endsWith(tt) || Ft.endsWith(":" + tt));
                        nt && et.add(nt);
                      }
                      et.size > 0 && B(et);
                    } else Ve.length > 0 && B(new Set(Ve));
                  }
                  const Et = we.result.match(/\[IMPACT:([^\]]+)\]/);
                  if (Et) {
                    const Ve = Et[1].split(",").map((et) => et.trim()).filter(Boolean);
                    if (Ve.length > 0 && r) {
                      const et = /* @__PURE__ */ new Set(), Dn = r.nodes.map((tt) => tt.id);
                      for (const tt of Ve) if (Dn.includes(tt)) et.add(tt);
                      else {
                        const nt = Dn.find((Ft) => Ft.endsWith(tt) || Ft.endsWith(":" + tt));
                        nt && et.add(nt);
                      }
                      et.size > 0 && O(et);
                    } else Ve.length > 0 && O(new Set(Ve));
                  }
                }
              }
              break;
            case "error":
              g(We.error ?? "Unknown error");
              break;
            case "done":
              un();
              break;
          }
        });
        await ne.chatStream(pe, lt);
      } catch (lt) {
        const We = lt instanceof Error ? lt.message : String(lt);
        g(We);
      } finally {
        T(false), G([]);
      }
    }, [
      u,
      He,
      Ti,
      ba,
      _c,
      Fo,
      xa,
      S,
      r,
      Xe
    ]), cm = z.useCallback(() => {
      const q = Nt.current;
      q && w && (q.stopChat(), T(false), G([]));
    }, [
      w
    ]), dm = z.useCallback(() => {
      d([]), G([]), g(null);
    }, []), fm = z.useCallback(async (q) => {
      if (ze) {
        oe({
          phase: "extracting",
          percent: 0,
          message: "Switching repository...",
          detail: `Loading ${q}`
        }), n("loading"), F(/* @__PURE__ */ new Set()), S(), j(), l(null), L(null), ke([]), xe(false), No(null);
        try {
          const ne = await _0(ze, (ye, $t, un) => {
            if (ye === "validating") oe({
              phase: "extracting",
              percent: 5,
              message: "Switching repository...",
              detail: "Validating"
            });
            else if (ye === "downloading") {
              const lt = un ? Math.round($t / un * 90) + 5 : 50, We = ($t / (1024 * 1024)).toFixed(1);
              oe({
                phase: "extracting",
                percent: lt,
                message: "Downloading graph...",
                detail: `${We} MB downloaded`
              });
            } else ye === "extracting" && oe({
              phase: "extracting",
              percent: 97,
              message: "Processing...",
              detail: "Extracting file contents"
            });
          }, void 0, q), de = ne.repoInfo.repoPath, pe = ne.repoInfo.name || de.split("/").pop() || "server-project";
          Qe(pe);
          const ge = el();
          for (const ye of ne.nodes) ge.addNode(ye);
          for (const ye of ne.relationships) ge.addRelationship(ye);
          i(ge);
          const ue = /* @__PURE__ */ new Map();
          for (const [ye, $t] of Object.entries(ne.fileContents)) ue.set(ye, $t);
          s(ue), n("exploring"), Zs() && Ti(pe), zo().catch((ye) => {
            var _a2;
            (ye == null ? void 0 : ye.name) === "WebGPUNotAvailableError" || ((_a2 = ye == null ? void 0 : ye.message) == null ? void 0 : _a2.includes("WebGPU")) ? zo("wasm").catch(console.warn) : console.warn("Embeddings auto-start failed:", ye);
          });
        } catch (ne) {
          console.error("Repo switch failed:", ne), oe({
            phase: "error",
            percent: 0,
            message: "Failed to switch repository",
            detail: ne instanceof Error ? ne.message : "Unknown error"
          }), setTimeout(() => {
            n("exploring"), oe(null);
          }, 3e3);
        }
      }
    }, [
      ze,
      oe,
      n,
      Qe,
      i,
      s,
      Ti,
      zo,
      F,
      S,
      j,
      l,
      L,
      ke,
      xe,
      No
    ]), hm = z.useCallback((q) => {
      ke((ne) => {
        const de = ne.find((ge) => ge.id === q), pe = ne.filter((ge) => ge.id !== q);
        return (de == null ? void 0 : de.nodeId) && de.source === "ai" && (pe.some((ue) => ue.nodeId === de.nodeId && ue.source === "ai") || N((ue) => {
          const ye = new Set(ue);
          return ye.delete(de.nodeId), ye;
        })), pe.length === 0 && !a && xe(false), pe;
      });
    }, [
      a
    ]), pm = z.useCallback(() => {
      ke([]), xe(false), No(null);
    }, []), gm = z.useCallback((q) => {
      I((ne) => ne.includes(q) ? ne.filter((de) => de !== q) : [
        ...ne,
        q
      ]);
    }, []), mm = z.useCallback((q) => {
      m((ne) => ne.includes(q) ? ne.filter((de) => de !== q) : [
        ...ne,
        q
      ]);
    }, []), vm = {
      viewMode: t,
      setViewMode: n,
      graph: r,
      setGraph: i,
      fileContents: o,
      setFileContents: s,
      selectedNode: a,
      setSelectedNode: l,
      isRightPanelOpen: c,
      setRightPanelOpen: h,
      rightPanelTab: f,
      setRightPanelTab: p,
      openCodePanel: y,
      openChatPanel: k,
      visibleLabels: b,
      toggleLabelVisibility: gm,
      visibleEdgeTypes: _,
      toggleEdgeVisibility: mm,
      depthFilter: v,
      setDepthFilter: E,
      highlightedNodeIds: A,
      setHighlightedNodeIds: F,
      aiCitationHighlightedNodeIds: C,
      aiToolHighlightedNodeIds: V,
      blastRadiusNodeIds: K,
      isAIHighlightsEnabled: re,
      toggleAIHighlights: J,
      clearAIToolHighlights: S,
      clearBlastRadius: j,
      queryResult: R,
      setQueryResult: L,
      clearQueryHighlights: H,
      animatedNodes: D,
      triggerNodeAnimation: ie,
      clearAnimations: _e,
      progress: Se,
      setProgress: oe,
      projectName: Z,
      setProjectName: Qe,
      serverBaseUrl: ze,
      setServerBaseUrl: _n,
      availableRepos: st,
      setAvailableRepos: mt,
      switchRepo: fm,
      runPipeline: em,
      runPipelineFromFiles: tm,
      runQuery: nm,
      isDatabaseReady: rm,
      embeddingStatus: Xe,
      embeddingProgress: ve,
      startEmbeddings: zo,
      semanticSearch: im,
      semanticSearchWithContext: om,
      isEmbeddingReady: Xe === "ready",
      testArrayParams: sm,
      llmSettings: vt,
      updateLLMSettings: am,
      isSettingsPanelOpen: se,
      setSettingsPanelOpen: U,
      isAgentReady: He,
      isAgentInitializing: ln,
      agentError: yt,
      chatMessages: u,
      isChatLoading: w,
      currentToolCalls: P,
      refreshLLMSettings: lm,
      initializeAgent: Ti,
      sendChatMessage: um,
      stopChatResponse: cm,
      clearChat: dm,
      codeReferences: fe,
      isCodePanelOpen: Ce,
      setCodePanelOpen: xe,
      addCodeReference: Fo,
      removeCodeReference: hm,
      clearAICodeReferences: xa,
      clearCodeReferences: pm,
      codeReferenceFocus: Le
    };
    return M.jsx(Xp.Provider, {
      value: vm,
      children: e
    });
  }, fc = () => {
    const e = z.useContext(Xp);
    if (!e) throw new Error("useAppState must be used within AppStateProvider");
    return e;
  }, b0 = ({ onFileSelect: e }) => {
    const [t, n] = z.useState(false), [r, i] = z.useState(null);
    return z.useCallback((o) => {
      o.preventDefault(), o.stopPropagation(), n(true);
    }, []), z.useCallback((o) => {
      o.preventDefault(), o.stopPropagation(), n(false);
    }, []), z.useCallback((o) => {
      o.preventDefault(), o.stopPropagation(), n(false);
      const s = o.dataTransfer.files;
      if (s.length > 0) {
        const a = s[0];
        a.name.endsWith(".zip") ? (e(a), i(null)) : i("Please drop a .zip file");
      }
    }, [
      e
    ]), z.useCallback((o) => {
      const s = o.target.files;
      if (s && s.length > 0) {
        const a = s[0];
        a.name.endsWith(".zip") ? (e(a), i(null)) : i("Please select a .zip file");
      }
    }, [
      e
    ]), M.jsxs("div", {
      className: "flex items-center justify-center min-h-screen p-8 bg-void",
      children: [
        M.jsxs("div", {
          className: "fixed inset-0 pointer-events-none",
          children: [
            M.jsx("div", {
              className: "absolute top-1/4 left-1/4 w-96 h-96 bg-accent/10 rounded-full blur-3xl"
            }),
            M.jsx("div", {
              className: "absolute bottom-1/4 right-1/4 w-96 h-96 bg-node-interface/10 rounded-full blur-3xl"
            })
          ]
        }),
        M.jsx("div", {
          className: "relative w-full max-w-lg",
          children: r && M.jsx("div", {
            className: "mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-sm text-center",
            children: r
          })
        })
      ]
    });
  }, x0 = ({ progress: e }) => M.jsxs("div", {
    className: "fixed inset-0 flex flex-col items-center justify-center bg-void z-50",
    children: [
      M.jsxs("div", {
        className: "absolute inset-0 pointer-events-none",
        children: [
          M.jsx("div", {
            className: "absolute top-1/3 left-1/3 w-96 h-96 bg-accent/10 rounded-full blur-3xl animate-pulse"
          }),
          M.jsx("div", {
            className: "absolute bottom-1/3 right-1/3 w-96 h-96 bg-node-interface/10 rounded-full blur-3xl animate-pulse"
          })
        ]
      }),
      M.jsxs("div", {
        className: "relative mb-10",
        children: [
          M.jsx("div", {
            className: "w-28 h-28 bg-gradient-to-br from-accent to-node-interface rounded-full animate-pulse-glow"
          }),
          M.jsx("div", {
            className: "absolute inset-0 w-28 h-28 bg-gradient-to-br from-accent to-node-interface rounded-full blur-xl opacity-50"
          })
        ]
      }),
      M.jsx("div", {
        className: "w-80 mb-4",
        children: M.jsx("div", {
          className: "h-1.5 bg-elevated rounded-full overflow-hidden",
          children: M.jsx("div", {
            className: "h-full bg-gradient-to-r from-accent to-node-interface rounded-full transition-all duration-300 ease-out",
            style: {
              width: `${e.percent}%`
            }
          })
        })
      }),
      M.jsxs("div", {
        className: "text-center",
        children: [
          M.jsxs("p", {
            className: "font-mono text-sm text-text-secondary mb-1",
            children: [
              e.message,
              M.jsx("span", {
                className: "animate-pulse",
                children: "|"
              })
            ]
          }),
          e.detail && M.jsx("p", {
            className: "font-mono text-xs text-text-muted truncate max-w-md",
            children: e.detail
          })
        ]
      }),
      e.stats && M.jsxs("div", {
        className: "mt-8 flex items-center gap-6 text-xs text-text-muted",
        children: [
          M.jsxs("div", {
            className: "flex items-center gap-2",
            children: [
              M.jsx("span", {
                className: "w-2 h-2 bg-node-file rounded-full"
              }),
              M.jsxs("span", {
                children: [
                  e.stats.filesProcessed,
                  " / ",
                  e.stats.totalFiles,
                  " files"
                ]
              })
            ]
          }),
          M.jsxs("div", {
            className: "flex items-center gap-2",
            children: [
              M.jsx("span", {
                className: "w-2 h-2 bg-node-function rounded-full"
              }),
              M.jsxs("span", {
                children: [
                  e.stats.nodesCreated,
                  " nodes"
                ]
              })
            ]
          })
        ]
      }),
      M.jsxs("p", {
        className: "mt-4 font-mono text-3xl font-semibold text-text-primary",
        children: [
          e.percent,
          "%"
        ]
      })
    ]
  });
  const C0 = (e) => e.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase(), T0 = (e) => e.replace(/^([A-Z])|[\s-_]+(\w)/g, (t, n, r) => r ? r.toUpperCase() : n.toLowerCase()), Bd = (e) => {
    const t = T0(e);
    return t.charAt(0).toUpperCase() + t.slice(1);
  }, Zp = (...e) => e.filter((t, n, r) => !!t && t.trim() !== "" && r.indexOf(t) === n).join(" ").trim(), R0 = (e) => {
    for (const t in e) if (t.startsWith("aria-") || t === "role" || t === "title") return true;
  };
  var A0 = {
    xmlns: "http://www.w3.org/2000/svg",
    width: 24,
    height: 24,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round",
    strokeLinejoin: "round"
  };
  const L0 = z.forwardRef(({ color: e = "currentColor", size: t = 24, strokeWidth: n = 2, absoluteStrokeWidth: r, className: i = "", children: o, iconNode: s, ...a }, l) => z.createElement("svg", {
    ref: l,
    ...A0,
    width: t,
    height: t,
    stroke: e,
    strokeWidth: r ? Number(n) * 24 / Number(t) : n,
    className: Zp("lucide", i),
    ...!o && !R0(a) && {
      "aria-hidden": "true"
    },
    ...a
  }, [
    ...s.map(([c, h]) => z.createElement(c, h)),
    ...Array.isArray(o) ? o : [
      o
    ]
  ]));
  const In = (e, t) => {
    const n = z.forwardRef(({ className: r, ...i }, o) => z.createElement(L0, {
      ref: o,
      iconNode: t,
      className: Zp(`lucide-${C0(Bd(e))}`, `lucide-${e}`, r),
      ...i
    }));
    return n.displayName = Bd(e), n;
  };
  const I0 = [
    [
      "path",
      {
        d: "m6 9 6 6 6-6",
        key: "qrunsl"
      }
    ]
  ], Md = In("chevron-down", I0);
  const D0 = [
    [
      "path",
      {
        d: "m18 15-6-6-6 6",
        key: "153udz"
      }
    ]
  ], P0 = In("chevron-up", D0);
  const N0 = [
    [
      "circle",
      {
        cx: "12",
        cy: "12",
        r: "3",
        key: "1v7zrd"
      }
    ],
    [
      "path",
      {
        d: "M3 7V5a2 2 0 0 1 2-2h2",
        key: "aa7l1z"
      }
    ],
    [
      "path",
      {
        d: "M17 3h2a2 2 0 0 1 2 2v2",
        key: "4qcy5o"
      }
    ],
    [
      "path",
      {
        d: "M21 17v2a2 2 0 0 1-2 2h-2",
        key: "6vwrx8"
      }
    ],
    [
      "path",
      {
        d: "M7 21H5a2 2 0 0 1-2-2v-2",
        key: "ioqczr"
      }
    ]
  ], F0 = In("focus", N0);
  const z0 = [
    [
      "path",
      {
        d: "M21 12a9 9 0 1 1-6.219-8.56",
        key: "13zald"
      }
    ]
  ], O0 = In("loader-circle", z0);
  const G0 = [
    [
      "path",
      {
        d: "M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z",
        key: "10ikf1"
      }
    ]
  ], U0 = In("play", G0);
  const B0 = [
    [
      "path",
      {
        d: "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8",
        key: "1357e3"
      }
    ],
    [
      "path",
      {
        d: "M3 3v5h5",
        key: "1xhq8a"
      }
    ]
  ], M0 = In("rotate-ccw", B0);
  const $0 = [
    [
      "path",
      {
        d: "M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z",
        key: "1s2grr"
      }
    ],
    [
      "path",
      {
        d: "M20 2v4",
        key: "1rf3ol"
      }
    ],
    [
      "path",
      {
        d: "M22 4h-4",
        key: "gwowj6"
      }
    ],
    [
      "circle",
      {
        cx: "4",
        cy: "20",
        r: "2",
        key: "6kqj1y"
      }
    ]
  ], j0 = In("sparkles", $0);
  const H0 = [
    [
      "path",
      {
        d: "M12 3v18",
        key: "108xh3"
      }
    ],
    [
      "rect",
      {
        width: "18",
        height: "18",
        x: "3",
        y: "3",
        rx: "2",
        key: "afitv7"
      }
    ],
    [
      "path",
      {
        d: "M3 9h18",
        key: "1pudct"
      }
    ],
    [
      "path",
      {
        d: "M3 15h18",
        key: "5xshup"
      }
    ]
  ], W0 = In("table", H0);
  const V0 = [
    [
      "path",
      {
        d: "M12 19h8",
        key: "baeox8"
      }
    ],
    [
      "path",
      {
        d: "m4 17 6-6-6-6",
        key: "1yngyt"
      }
    ]
  ], $d = In("terminal", V0);
  const K0 = [
    [
      "path",
      {
        d: "M18 6 6 18",
        key: "1bl5f8"
      }
    ],
    [
      "path",
      {
        d: "m6 6 12 12",
        key: "d8bk6v"
      }
    ]
  ], Y0 = In("x", K0);
  function Q0(e, t) {
    if (typeof e != "object" || !e) return e;
    var n = e[Symbol.toPrimitive];
    if (n !== void 0) {
      var r = n.call(e, t);
      if (typeof r != "object") return r;
      throw new TypeError("@@toPrimitive must return a primitive value.");
    }
    return String(e);
  }
  function ao(e) {
    var t = Q0(e, "string");
    return typeof t == "symbol" ? t : t + "";
  }
  function Ct(e, t) {
    if (!(e instanceof t)) throw new TypeError("Cannot call a class as a function");
  }
  function jd(e, t) {
    for (var n = 0; n < t.length; n++) {
      var r = t[n];
      r.enumerable = r.enumerable || false, r.configurable = true, "value" in r && (r.writable = true), Object.defineProperty(e, ao(r.key), r);
    }
  }
  function Tt(e, t, n) {
    return t && jd(e.prototype, t), n && jd(e, n), Object.defineProperty(e, "prototype", {
      writable: false
    }), e;
  }
  function mi(e) {
    return mi = Object.setPrototypeOf ? Object.getPrototypeOf.bind() : function(t) {
      return t.__proto__ || Object.getPrototypeOf(t);
    }, mi(e);
  }
  function qp() {
    try {
      var e = !Boolean.prototype.valueOf.call(Reflect.construct(Boolean, [], function() {
      }));
    } catch {
    }
    return (qp = function() {
      return !!e;
    })();
  }
  function X0(e) {
    if (e === void 0) throw new ReferenceError("this hasn't been initialised - super() hasn't been called");
    return e;
  }
  function Z0(e, t) {
    if (t && (typeof t == "object" || typeof t == "function")) return t;
    if (t !== void 0) throw new TypeError("Derived constructors may only return object or undefined");
    return X0(e);
  }
  function sn(e, t, n) {
    return t = mi(t), Z0(e, qp() ? Reflect.construct(t, n || [], mi(e).constructor) : t.apply(e, n));
  }
  function uu(e, t) {
    return uu = Object.setPrototypeOf ? Object.setPrototypeOf.bind() : function(n, r) {
      return n.__proto__ = r, n;
    }, uu(e, t);
  }
  function an(e, t) {
    if (typeof t != "function" && t !== null) throw new TypeError("Super expression must either be null or a function");
    e.prototype = Object.create(t && t.prototype, {
      constructor: {
        value: e,
        writable: true,
        configurable: true
      }
    }), Object.defineProperty(e, "prototype", {
      writable: false
    }), t && uu(e, t);
  }
  function q0(e) {
    if (Array.isArray(e)) return e;
  }
  function J0(e, t) {
    var n = e == null ? null : typeof Symbol < "u" && e[Symbol.iterator] || e["@@iterator"];
    if (n != null) {
      var r, i, o, s, a = [], l = true, c = false;
      try {
        if (o = (n = n.call(e)).next, t === 0) {
          if (Object(n) !== n) return;
          l = false;
        } else for (; !(l = (r = o.call(n)).done) && (a.push(r.value), a.length !== t); l = true) ;
      } catch (h) {
        c = true, i = h;
      } finally {
        try {
          if (!l && n.return != null && (s = n.return(), Object(s) !== s)) return;
        } finally {
          if (c) throw i;
        }
      }
      return a;
    }
  }
  function cu(e, t) {
    (t == null || t > e.length) && (t = e.length);
    for (var n = 0, r = Array(t); n < t; n++) r[n] = e[n];
    return r;
  }
  function Jp(e, t) {
    if (e) {
      if (typeof e == "string") return cu(e, t);
      var n = {}.toString.call(e).slice(8, -1);
      return n === "Object" && e.constructor && (n = e.constructor.name), n === "Map" || n === "Set" ? Array.from(e) : n === "Arguments" || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(n) ? cu(e, t) : void 0;
    }
  }
  function ew() {
    throw new TypeError(`Invalid attempt to destructure non-iterable instance.
In order to be iterable, non-array objects must have a [Symbol.iterator]() method.`);
  }
  function vi(e, t) {
    return q0(e) || J0(e, t) || Jp(e, t) || ew();
  }
  var tl = {
    black: "#000000",
    silver: "#C0C0C0",
    gray: "#808080",
    grey: "#808080",
    white: "#FFFFFF",
    maroon: "#800000",
    red: "#FF0000",
    purple: "#800080",
    fuchsia: "#FF00FF",
    green: "#008000",
    lime: "#00FF00",
    olive: "#808000",
    yellow: "#FFFF00",
    navy: "#000080",
    blue: "#0000FF",
    teal: "#008080",
    aqua: "#00FFFF",
    darkblue: "#00008B",
    mediumblue: "#0000CD",
    darkgreen: "#006400",
    darkcyan: "#008B8B",
    deepskyblue: "#00BFFF",
    darkturquoise: "#00CED1",
    mediumspringgreen: "#00FA9A",
    springgreen: "#00FF7F",
    cyan: "#00FFFF",
    midnightblue: "#191970",
    dodgerblue: "#1E90FF",
    lightseagreen: "#20B2AA",
    forestgreen: "#228B22",
    seagreen: "#2E8B57",
    darkslategray: "#2F4F4F",
    darkslategrey: "#2F4F4F",
    limegreen: "#32CD32",
    mediumseagreen: "#3CB371",
    turquoise: "#40E0D0",
    royalblue: "#4169E1",
    steelblue: "#4682B4",
    darkslateblue: "#483D8B",
    mediumturquoise: "#48D1CC",
    indigo: "#4B0082",
    darkolivegreen: "#556B2F",
    cadetblue: "#5F9EA0",
    cornflowerblue: "#6495ED",
    rebeccapurple: "#663399",
    mediumaquamarine: "#66CDAA",
    dimgray: "#696969",
    dimgrey: "#696969",
    slateblue: "#6A5ACD",
    olivedrab: "#6B8E23",
    slategray: "#708090",
    slategrey: "#708090",
    lightslategray: "#778899",
    lightslategrey: "#778899",
    mediumslateblue: "#7B68EE",
    lawngreen: "#7CFC00",
    chartreuse: "#7FFF00",
    aquamarine: "#7FFFD4",
    skyblue: "#87CEEB",
    lightskyblue: "#87CEFA",
    blueviolet: "#8A2BE2",
    darkred: "#8B0000",
    darkmagenta: "#8B008B",
    saddlebrown: "#8B4513",
    darkseagreen: "#8FBC8F",
    lightgreen: "#90EE90",
    mediumpurple: "#9370DB",
    darkviolet: "#9400D3",
    palegreen: "#98FB98",
    darkorchid: "#9932CC",
    yellowgreen: "#9ACD32",
    sienna: "#A0522D",
    brown: "#A52A2A",
    darkgray: "#A9A9A9",
    darkgrey: "#A9A9A9",
    lightblue: "#ADD8E6",
    greenyellow: "#ADFF2F",
    paleturquoise: "#AFEEEE",
    lightsteelblue: "#B0C4DE",
    powderblue: "#B0E0E6",
    firebrick: "#B22222",
    darkgoldenrod: "#B8860B",
    mediumorchid: "#BA55D3",
    rosybrown: "#BC8F8F",
    darkkhaki: "#BDB76B",
    mediumvioletred: "#C71585",
    indianred: "#CD5C5C",
    peru: "#CD853F",
    chocolate: "#D2691E",
    tan: "#D2B48C",
    lightgray: "#D3D3D3",
    lightgrey: "#D3D3D3",
    thistle: "#D8BFD8",
    orchid: "#DA70D6",
    goldenrod: "#DAA520",
    palevioletred: "#DB7093",
    crimson: "#DC143C",
    gainsboro: "#DCDCDC",
    plum: "#DDA0DD",
    burlywood: "#DEB887",
    lightcyan: "#E0FFFF",
    lavender: "#E6E6FA",
    darksalmon: "#E9967A",
    violet: "#EE82EE",
    palegoldenrod: "#EEE8AA",
    lightcoral: "#F08080",
    khaki: "#F0E68C",
    aliceblue: "#F0F8FF",
    honeydew: "#F0FFF0",
    azure: "#F0FFFF",
    sandybrown: "#F4A460",
    wheat: "#F5DEB3",
    beige: "#F5F5DC",
    whitesmoke: "#F5F5F5",
    mintcream: "#F5FFFA",
    ghostwhite: "#F8F8FF",
    salmon: "#FA8072",
    antiquewhite: "#FAEBD7",
    linen: "#FAF0E6",
    lightgoldenrodyellow: "#FAFAD2",
    oldlace: "#FDF5E6",
    magenta: "#FF00FF",
    deeppink: "#FF1493",
    orangered: "#FF4500",
    tomato: "#FF6347",
    hotpink: "#FF69B4",
    coral: "#FF7F50",
    darkorange: "#FF8C00",
    lightsalmon: "#FFA07A",
    orange: "#FFA500",
    lightpink: "#FFB6C1",
    pink: "#FFC0CB",
    gold: "#FFD700",
    peachpuff: "#FFDAB9",
    navajowhite: "#FFDEAD",
    moccasin: "#FFE4B5",
    bisque: "#FFE4C4",
    mistyrose: "#FFE4E1",
    blanchedalmond: "#FFEBCD",
    papayawhip: "#FFEFD5",
    lavenderblush: "#FFF0F5",
    seashell: "#FFF5EE",
    cornsilk: "#FFF8DC",
    lemonchiffon: "#FFFACD",
    floralwhite: "#FFFAF0",
    snow: "#FFFAFA",
    lightyellow: "#FFFFE0",
    ivory: "#FFFFF0"
  }, eg = new Int8Array(4), nl = new Int32Array(eg.buffer, 0, 1), tw = new Float32Array(eg.buffer, 0, 1), nw = /^\s*rgba?\s*\(/, rw = /^\s*rgba?\s*\(\s*([0-9]*)\s*,\s*([0-9]*)\s*,\s*([0-9]*)(?:\s*,\s*(.*)?)?\)\s*$/;
  function iw(e) {
    var t = 0, n = 0, r = 0, i = 1;
    if (e[0] === "#") e.length === 4 ? (t = parseInt(e.charAt(1) + e.charAt(1), 16), n = parseInt(e.charAt(2) + e.charAt(2), 16), r = parseInt(e.charAt(3) + e.charAt(3), 16)) : (t = parseInt(e.charAt(1) + e.charAt(2), 16), n = parseInt(e.charAt(3) + e.charAt(4), 16), r = parseInt(e.charAt(5) + e.charAt(6), 16)), e.length === 9 && (i = parseInt(e.charAt(7) + e.charAt(8), 16) / 255);
    else if (nw.test(e)) {
      var o = e.match(rw);
      o && (t = +o[1], n = +o[2], r = +o[3], o[4] && (i = +o[4]));
    }
    return {
      r: t,
      g: n,
      b: r,
      a: i
    };
  }
  var ai = {};
  for (var ts in tl) ai[ts] = _i(tl[ts]), ai[tl[ts]] = ai[ts];
  function tg(e, t, n, r, i) {
    return nl[0] = r << 24 | n << 16 | t << 8 | e, nl[0] = nl[0] & 4278190079, tw[0];
  }
  function _i(e) {
    if (e = e.toLowerCase(), typeof ai[e] < "u") return ai[e];
    var t = iw(e), n = t.r, r = t.g, i = t.b, o = t.a;
    o = o * 255 | 0;
    var s = tg(n, r, i, o);
    return ai[e] = s, s;
  }
  var rl = {};
  function ng(e) {
    if (typeof rl[e] < "u") return rl[e];
    var t = (e & 16711680) >>> 16, n = (e & 65280) >>> 8, r = e & 255, i = 255, o = tg(t, n, r, i);
    return rl[e] = o, o;
  }
  function Hd(e, t, n, r) {
    return n + (t << 8) + (e << 16);
  }
  function Wd(e, t, n, r, i, o) {
    var s = Math.floor(n / o * i), a = Math.floor(e.drawingBufferHeight / o - r / o * i), l = new Uint8Array(4);
    e.bindFramebuffer(e.FRAMEBUFFER, t), e.readPixels(s, a, 1, 1, e.RGBA, e.UNSIGNED_BYTE, l);
    var c = vi(l, 4), h = c[0], f = c[1], p = c[2], y = c[3];
    return [
      h,
      f,
      p,
      y
    ];
  }
  function $(e, t, n) {
    return (t = ao(t)) in e ? Object.defineProperty(e, t, {
      value: n,
      enumerable: true,
      configurable: true,
      writable: true
    }) : e[t] = n, e;
  }
  function Vd(e, t) {
    var n = Object.keys(e);
    if (Object.getOwnPropertySymbols) {
      var r = Object.getOwnPropertySymbols(e);
      t && (r = r.filter(function(i) {
        return Object.getOwnPropertyDescriptor(e, i).enumerable;
      })), n.push.apply(n, r);
    }
    return n;
  }
  function te(e) {
    for (var t = 1; t < arguments.length; t++) {
      var n = arguments[t] != null ? arguments[t] : {};
      t % 2 ? Vd(Object(n), true).forEach(function(r) {
        $(e, r, n[r]);
      }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(n)) : Vd(Object(n)).forEach(function(r) {
        Object.defineProperty(e, r, Object.getOwnPropertyDescriptor(n, r));
      });
    }
    return e;
  }
  function ow(e, t) {
    for (; !{}.hasOwnProperty.call(e, t) && (e = mi(e)) !== null; ) ;
    return e;
  }
  function du() {
    return du = typeof Reflect < "u" && Reflect.get ? Reflect.get.bind() : function(e, t, n) {
      var r = ow(e, t);
      if (r) {
        var i = Object.getOwnPropertyDescriptor(r, t);
        return i.get ? i.get.call(arguments.length < 3 ? e : n) : i.value;
      }
    }, du.apply(null, arguments);
  }
  function rg(e, t, n, r) {
    var i = du(mi(e.prototype), t, n);
    return typeof i == "function" ? function(o) {
      return i.apply(n, o);
    } : i;
  }
  function sw(e) {
    return e.normalized ? 1 : e.size;
  }
  function il(e) {
    var t = 0;
    return e.forEach(function(n) {
      return t += sw(n);
    }), t;
  }
  function ig(e, t, n) {
    var r = e === "VERTEX" ? t.VERTEX_SHADER : t.FRAGMENT_SHADER, i = t.createShader(r);
    if (i === null) throw new Error("loadShader: error while creating the shader");
    t.shaderSource(i, n), t.compileShader(i);
    var o = t.getShaderParameter(i, t.COMPILE_STATUS);
    if (!o) {
      var s = t.getShaderInfoLog(i);
      throw t.deleteShader(i), new Error(`loadShader: error while compiling the shader:
`.concat(s, `
`).concat(n));
    }
    return i;
  }
  function aw(e, t) {
    return ig("VERTEX", e, t);
  }
  function lw(e, t) {
    return ig("FRAGMENT", e, t);
  }
  function uw(e, t) {
    var n = e.createProgram();
    if (n === null) throw new Error("loadProgram: error while creating the program.");
    var r, i;
    for (r = 0, i = t.length; r < i; r++) e.attachShader(n, t[r]);
    e.linkProgram(n);
    var o = e.getProgramParameter(n, e.LINK_STATUS);
    if (!o) throw e.deleteProgram(n), new Error("loadProgram: error while linking the program.");
    return n;
  }
  function Kd(e) {
    var t = e.gl, n = e.buffer, r = e.program, i = e.vertexShader, o = e.fragmentShader;
    t.deleteShader(i), t.deleteShader(o), t.deleteProgram(r), t.deleteBuffer(n);
  }
  var Yd = `#define PICKING_MODE
`, cw = $($($($($($($($({}, WebGL2RenderingContext.BOOL, 1), WebGL2RenderingContext.BYTE, 1), WebGL2RenderingContext.UNSIGNED_BYTE, 1), WebGL2RenderingContext.SHORT, 2), WebGL2RenderingContext.UNSIGNED_SHORT, 2), WebGL2RenderingContext.INT, 4), WebGL2RenderingContext.UNSIGNED_INT, 4), WebGL2RenderingContext.FLOAT, 4), og = function() {
    function e(t, n, r) {
      Ct(this, e), $(this, "array", new Float32Array()), $(this, "constantArray", new Float32Array()), $(this, "capacity", 0), $(this, "verticesCount", 0);
      var i = this.getDefinition();
      if (this.VERTICES = i.VERTICES, this.VERTEX_SHADER_SOURCE = i.VERTEX_SHADER_SOURCE, this.FRAGMENT_SHADER_SOURCE = i.FRAGMENT_SHADER_SOURCE, this.UNIFORMS = i.UNIFORMS, this.ATTRIBUTES = i.ATTRIBUTES, this.METHOD = i.METHOD, this.CONSTANT_ATTRIBUTES = "CONSTANT_ATTRIBUTES" in i ? i.CONSTANT_ATTRIBUTES : [], this.CONSTANT_DATA = "CONSTANT_DATA" in i ? i.CONSTANT_DATA : [], this.isInstanced = "CONSTANT_ATTRIBUTES" in i, this.ATTRIBUTES_ITEMS_COUNT = il(this.ATTRIBUTES), this.STRIDE = this.VERTICES * this.ATTRIBUTES_ITEMS_COUNT, this.renderer = r, this.normalProgram = this.getProgramInfo("normal", t, i.VERTEX_SHADER_SOURCE, i.FRAGMENT_SHADER_SOURCE, null), this.pickProgram = n ? this.getProgramInfo("pick", t, Yd + i.VERTEX_SHADER_SOURCE, Yd + i.FRAGMENT_SHADER_SOURCE, n) : null, this.isInstanced) {
        var o = il(this.CONSTANT_ATTRIBUTES);
        if (this.CONSTANT_DATA.length !== this.VERTICES) throw new Error("Program: error while getting constant data (expected ".concat(this.VERTICES, " items, received ").concat(this.CONSTANT_DATA.length, " instead)"));
        this.constantArray = new Float32Array(this.CONSTANT_DATA.length * o);
        for (var s = 0; s < this.CONSTANT_DATA.length; s++) {
          var a = this.CONSTANT_DATA[s];
          if (a.length !== o) throw new Error("Program: error while getting constant data (one vector has ".concat(a.length, " items instead of ").concat(o, ")"));
          for (var l = 0; l < a.length; l++) this.constantArray[s * o + l] = a[l];
        }
        this.STRIDE = this.ATTRIBUTES_ITEMS_COUNT;
      }
    }
    return Tt(e, [
      {
        key: "kill",
        value: function() {
          Kd(this.normalProgram), this.pickProgram && (Kd(this.pickProgram), this.pickProgram = null);
        }
      },
      {
        key: "getProgramInfo",
        value: function(n, r, i, o, s) {
          var a = this.getDefinition(), l = r.createBuffer();
          if (l === null) throw new Error("Program: error while creating the WebGL buffer.");
          var c = aw(r, i), h = lw(r, o), f = uw(r, [
            c,
            h
          ]), p = {};
          a.UNIFORMS.forEach(function(b) {
            var I = r.getUniformLocation(f, b);
            I && (p[b] = I);
          });
          var y = {};
          a.ATTRIBUTES.forEach(function(b) {
            y[b.name] = r.getAttribLocation(f, b.name);
          });
          var k;
          if ("CONSTANT_ATTRIBUTES" in a && (a.CONSTANT_ATTRIBUTES.forEach(function(b) {
            y[b.name] = r.getAttribLocation(f, b.name);
          }), k = r.createBuffer(), k === null)) throw new Error("Program: error while creating the WebGL constant buffer.");
          return {
            name: n,
            program: f,
            gl: r,
            frameBuffer: s,
            buffer: l,
            constantBuffer: k || {},
            uniformLocations: p,
            attributeLocations: y,
            isPicking: n === "pick",
            vertexShader: c,
            fragmentShader: h
          };
        }
      },
      {
        key: "bindProgram",
        value: function(n) {
          var r = this, i = 0, o = n.gl, s = n.buffer;
          this.isInstanced ? (o.bindBuffer(o.ARRAY_BUFFER, n.constantBuffer), i = 0, this.CONSTANT_ATTRIBUTES.forEach(function(a) {
            return i += r.bindAttribute(a, n, i, false);
          }), o.bufferData(o.ARRAY_BUFFER, this.constantArray, o.STATIC_DRAW), o.bindBuffer(o.ARRAY_BUFFER, n.buffer), i = 0, this.ATTRIBUTES.forEach(function(a) {
            return i += r.bindAttribute(a, n, i, true);
          }), o.bufferData(o.ARRAY_BUFFER, this.array, o.DYNAMIC_DRAW)) : (o.bindBuffer(o.ARRAY_BUFFER, s), i = 0, this.ATTRIBUTES.forEach(function(a) {
            return i += r.bindAttribute(a, n, i);
          }), o.bufferData(o.ARRAY_BUFFER, this.array, o.DYNAMIC_DRAW)), o.bindBuffer(o.ARRAY_BUFFER, null);
        }
      },
      {
        key: "unbindProgram",
        value: function(n) {
          var r = this;
          this.isInstanced ? (this.CONSTANT_ATTRIBUTES.forEach(function(i) {
            return r.unbindAttribute(i, n, false);
          }), this.ATTRIBUTES.forEach(function(i) {
            return r.unbindAttribute(i, n, true);
          })) : this.ATTRIBUTES.forEach(function(i) {
            return r.unbindAttribute(i, n);
          });
        }
      },
      {
        key: "bindAttribute",
        value: function(n, r, i, o) {
          var s = cw[n.type];
          if (typeof s != "number") throw new Error('Program.bind: yet unsupported attribute type "'.concat(n.type, '"'));
          var a = r.attributeLocations[n.name], l = r.gl;
          if (a !== -1) {
            l.enableVertexAttribArray(a);
            var c = this.isInstanced ? (o ? this.ATTRIBUTES_ITEMS_COUNT : il(this.CONSTANT_ATTRIBUTES)) * Float32Array.BYTES_PER_ELEMENT : this.ATTRIBUTES_ITEMS_COUNT * Float32Array.BYTES_PER_ELEMENT;
            if (l.vertexAttribPointer(a, n.size, n.type, n.normalized || false, c, i), this.isInstanced && o) if (l instanceof WebGL2RenderingContext) l.vertexAttribDivisor(a, 1);
            else {
              var h = l.getExtension("ANGLE_instanced_arrays");
              h && h.vertexAttribDivisorANGLE(a, 1);
            }
          }
          return n.size * s;
        }
      },
      {
        key: "unbindAttribute",
        value: function(n, r, i) {
          var o = r.attributeLocations[n.name], s = r.gl;
          if (o !== -1 && (s.disableVertexAttribArray(o), this.isInstanced && i)) if (s instanceof WebGL2RenderingContext) s.vertexAttribDivisor(o, 0);
          else {
            var a = s.getExtension("ANGLE_instanced_arrays");
            a && a.vertexAttribDivisorANGLE(o, 0);
          }
        }
      },
      {
        key: "reallocate",
        value: function(n) {
          n !== this.capacity && (this.capacity = n, this.verticesCount = this.VERTICES * n, this.array = new Float32Array(this.isInstanced ? this.capacity * this.ATTRIBUTES_ITEMS_COUNT : this.verticesCount * this.ATTRIBUTES_ITEMS_COUNT));
        }
      },
      {
        key: "hasNothingToRender",
        value: function() {
          return this.verticesCount === 0;
        }
      },
      {
        key: "renderProgram",
        value: function(n, r) {
          var i = r.gl, o = r.program;
          i.enable(i.BLEND), i.useProgram(o), this.setUniforms(n, r), this.drawWebGL(this.METHOD, r);
        }
      },
      {
        key: "render",
        value: function(n) {
          this.hasNothingToRender() || (this.pickProgram && (this.pickProgram.gl.viewport(0, 0, n.width * n.pixelRatio / n.downSizingRatio, n.height * n.pixelRatio / n.downSizingRatio), this.bindProgram(this.pickProgram), this.renderProgram(te(te({}, n), {}, {
            pixelRatio: n.pixelRatio / n.downSizingRatio
          }), this.pickProgram), this.unbindProgram(this.pickProgram)), this.normalProgram.gl.viewport(0, 0, n.width * n.pixelRatio, n.height * n.pixelRatio), this.bindProgram(this.normalProgram), this.renderProgram(n, this.normalProgram), this.unbindProgram(this.normalProgram));
        }
      },
      {
        key: "drawWebGL",
        value: function(n, r) {
          var i = r.gl, o = r.frameBuffer;
          if (i.bindFramebuffer(i.FRAMEBUFFER, o), !this.isInstanced) i.drawArrays(n, 0, this.verticesCount);
          else if (i instanceof WebGL2RenderingContext) i.drawArraysInstanced(n, 0, this.VERTICES, this.capacity);
          else {
            var s = i.getExtension("ANGLE_instanced_arrays");
            s && s.drawArraysInstancedANGLE(n, 0, this.VERTICES, this.capacity);
          }
        }
      }
    ]);
  }(), dw = function(e) {
    function t() {
      return Ct(this, t), sn(this, t, arguments);
    }
    return an(t, e), Tt(t, [
      {
        key: "kill",
        value: function() {
          rg(t, "kill", this)([]);
        }
      },
      {
        key: "process",
        value: function(r, i, o) {
          var s = i * this.STRIDE;
          if (o.hidden) {
            for (var a = s + this.STRIDE; s < a; s++) this.array[s] = 0;
            return;
          }
          return this.processVisibleItem(ng(r), s, o);
        }
      }
    ]);
  }(og), ya = function(e) {
    function t() {
      var n;
      Ct(this, t);
      for (var r = arguments.length, i = new Array(r), o = 0; o < r; o++) i[o] = arguments[o];
      return n = sn(this, t, [].concat(i)), $(n, "drawLabel", void 0), n;
    }
    return an(t, e), Tt(t, [
      {
        key: "kill",
        value: function() {
          rg(t, "kill", this)([]);
        }
      },
      {
        key: "process",
        value: function(r, i, o, s, a) {
          var l = i * this.STRIDE;
          if (a.hidden || o.hidden || s.hidden) {
            for (var c = l + this.STRIDE; l < c; l++) this.array[l] = 0;
            return;
          }
          return this.processVisibleItem(ng(r), l, o, s, a);
        }
      }
    ]);
  }(og);
  function fw(e, t) {
    return function() {
      function n(r, i, o) {
        Ct(this, n), $(this, "drawLabel", t), this.programs = e.map(function(s) {
          return new s(r, i, o);
        });
      }
      return Tt(n, [
        {
          key: "reallocate",
          value: function(i) {
            this.programs.forEach(function(o) {
              return o.reallocate(i);
            });
          }
        },
        {
          key: "process",
          value: function(i, o, s, a, l) {
            this.programs.forEach(function(c) {
              return c.process(i, o, s, a, l);
            });
          }
        },
        {
          key: "render",
          value: function(i) {
            this.programs.forEach(function(o) {
              return o.render(i);
            });
          }
        },
        {
          key: "kill",
          value: function() {
            this.programs.forEach(function(i) {
              return i.kill();
            });
          }
        }
      ]);
    }();
  }
  function hw(e, t, n, r, i) {
    var o = i.edgeLabelSize, s = i.edgeLabelFont, a = i.edgeLabelWeight, l = i.edgeLabelColor.attribute ? t[i.edgeLabelColor.attribute] || i.edgeLabelColor.color || "#000" : i.edgeLabelColor.color, c = t.label;
    if (c) {
      e.fillStyle = l, e.font = "".concat(a, " ").concat(o, "px ").concat(s);
      var h = n.size, f = r.size, p = n.x, y = n.y, k = r.x, b = r.y, I = (p + k) / 2, _ = (y + b) / 2, m = k - p, v = b - y, E = Math.sqrt(m * m + v * v);
      if (!(E < h + f)) {
        p += m * h / E, y += v * h / E, k -= m * f / E, b -= v * f / E, I = (p + k) / 2, _ = (y + b) / 2, m = k - p, v = b - y, E = Math.sqrt(m * m + v * v);
        var A = e.measureText(c).width;
        if (A > E) {
          var F = "\u2026";
          for (c = c + F, A = e.measureText(c).width; A > E && c.length > 1; ) c = c.slice(0, -2) + F, A = e.measureText(c).width;
          if (c.length < 4) return;
        }
        var R;
        m > 0 ? v > 0 ? R = Math.acos(m / E) : R = Math.asin(v / E) : v > 0 ? R = Math.acos(m / E) + Math.PI : R = Math.asin(m / E) + Math.PI / 2, e.save(), e.translate(I, _), e.rotate(R), e.fillText(c, -A / 2, t.size / 2 + o), e.restore();
      }
    }
  }
  function sg(e, t, n) {
    if (t.label) {
      var r = n.labelSize, i = n.labelFont, o = n.labelWeight, s = n.labelColor.attribute ? t[n.labelColor.attribute] || n.labelColor.color || "#000" : n.labelColor.color;
      e.fillStyle = s, e.font = "".concat(o, " ").concat(r, "px ").concat(i), e.fillText(t.label, t.x + t.size + 3, t.y + r / 3);
    }
  }
  function pw(e, t, n) {
    var r = n.labelSize, i = n.labelFont, o = n.labelWeight;
    e.font = "".concat(o, " ").concat(r, "px ").concat(i), e.fillStyle = "#FFF", e.shadowOffsetX = 0, e.shadowOffsetY = 0, e.shadowBlur = 8, e.shadowColor = "#000";
    var s = 2;
    if (typeof t.label == "string") {
      var a = e.measureText(t.label).width, l = Math.round(a + 5), c = Math.round(r + 2 * s), h = Math.max(t.size, r / 2) + s, f = Math.asin(c / 2 / h), p = Math.sqrt(Math.abs(Math.pow(h, 2) - Math.pow(c / 2, 2)));
      e.beginPath(), e.moveTo(t.x + p, t.y + c / 2), e.lineTo(t.x + h + l, t.y + c / 2), e.lineTo(t.x + h + l, t.y - c / 2), e.lineTo(t.x + p, t.y - c / 2), e.arc(t.x, t.y, h, f, -f), e.closePath(), e.fill();
    } else e.beginPath(), e.arc(t.x, t.y, t.size + s, 0, Math.PI * 2), e.closePath(), e.fill();
    e.shadowOffsetX = 0, e.shadowOffsetY = 0, e.shadowBlur = 0, sg(e, t, n);
  }
  var gw = `
precision highp float;

varying vec4 v_color;
varying vec2 v_diffVector;
varying float v_radius;

uniform float u_correctionRatio;

const vec4 transparent = vec4(0.0, 0.0, 0.0, 0.0);

void main(void) {
  float border = u_correctionRatio * 2.0;
  float dist = length(v_diffVector) - v_radius + border;

  // No antialiasing for picking mode:
  #ifdef PICKING_MODE
  if (dist > border)
    gl_FragColor = transparent;
  else
    gl_FragColor = v_color;

  #else
  float t = 0.0;
  if (dist > border)
    t = 1.0;
  else if (dist > 0.0)
    t = dist / border;

  gl_FragColor = mix(v_color, transparent, t);
  #endif
}
`, mw = gw, vw = `
attribute vec4 a_id;
attribute vec4 a_color;
attribute vec2 a_position;
attribute float a_size;
attribute float a_angle;

uniform mat3 u_matrix;
uniform float u_sizeRatio;
uniform float u_correctionRatio;

varying vec4 v_color;
varying vec2 v_diffVector;
varying float v_radius;
varying float v_border;

const float bias = 255.0 / 254.0;

void main() {
  float size = a_size * u_correctionRatio / u_sizeRatio * 4.0;
  vec2 diffVector = size * vec2(cos(a_angle), sin(a_angle));
  vec2 position = a_position + diffVector;
  gl_Position = vec4(
    (u_matrix * vec3(position, 1)).xy,
    0,
    1
  );

  v_diffVector = diffVector;
  v_radius = size / 2.0;

  #ifdef PICKING_MODE
  // For picking mode, we use the ID as the color:
  v_color = a_id;
  #else
  // For normal mode, we use the color:
  v_color = a_color;
  #endif

  v_color.a *= bias;
}
`, yw = vw, ag = WebGLRenderingContext, Qd = ag.UNSIGNED_BYTE, ol = ag.FLOAT, ww = [
    "u_sizeRatio",
    "u_correctionRatio",
    "u_matrix"
  ], wa = function(e) {
    function t() {
      return Ct(this, t), sn(this, t, arguments);
    }
    return an(t, e), Tt(t, [
      {
        key: "getDefinition",
        value: function() {
          return {
            VERTICES: 3,
            VERTEX_SHADER_SOURCE: yw,
            FRAGMENT_SHADER_SOURCE: mw,
            METHOD: WebGLRenderingContext.TRIANGLES,
            UNIFORMS: ww,
            ATTRIBUTES: [
              {
                name: "a_position",
                size: 2,
                type: ol
              },
              {
                name: "a_size",
                size: 1,
                type: ol
              },
              {
                name: "a_color",
                size: 4,
                type: Qd,
                normalized: true
              },
              {
                name: "a_id",
                size: 4,
                type: Qd,
                normalized: true
              }
            ],
            CONSTANT_ATTRIBUTES: [
              {
                name: "a_angle",
                size: 1,
                type: ol
              }
            ],
            CONSTANT_DATA: [
              [
                t.ANGLE_1
              ],
              [
                t.ANGLE_2
              ],
              [
                t.ANGLE_3
              ]
            ]
          };
        }
      },
      {
        key: "processVisibleItem",
        value: function(r, i, o) {
          var s = this.array, a = _i(o.color);
          s[i++] = o.x, s[i++] = o.y, s[i++] = o.size, s[i++] = a, s[i++] = r;
        }
      },
      {
        key: "setUniforms",
        value: function(r, i) {
          var o = i.gl, s = i.uniformLocations, a = s.u_sizeRatio, l = s.u_correctionRatio, c = s.u_matrix;
          o.uniform1f(l, r.correctionRatio), o.uniform1f(a, r.sizeRatio), o.uniformMatrix3fv(c, false, r.matrix);
        }
      }
    ]);
  }(dw);
  $(wa, "ANGLE_1", 0);
  $(wa, "ANGLE_2", 2 * Math.PI / 3);
  $(wa, "ANGLE_3", 4 * Math.PI / 3);
  var Ew = `
precision mediump float;

varying vec4 v_color;

void main(void) {
  gl_FragColor = v_color;
}
`, Sw = Ew, _w = `
attribute vec2 a_position;
attribute vec2 a_normal;
attribute float a_radius;
attribute vec3 a_barycentric;

#ifdef PICKING_MODE
attribute vec4 a_id;
#else
attribute vec4 a_color;
#endif

uniform mat3 u_matrix;
uniform float u_sizeRatio;
uniform float u_correctionRatio;
uniform float u_minEdgeThickness;
uniform float u_lengthToThicknessRatio;
uniform float u_widenessToThicknessRatio;

varying vec4 v_color;

const float bias = 255.0 / 254.0;

void main() {
  float minThickness = u_minEdgeThickness;

  float normalLength = length(a_normal);
  vec2 unitNormal = a_normal / normalLength;

  // These first computations are taken from edge.vert.glsl and
  // edge.clamped.vert.glsl. Please read it to get better comments on what's
  // happening:
  float pixelsThickness = max(normalLength / u_sizeRatio, minThickness);
  float webGLThickness = pixelsThickness * u_correctionRatio;
  float webGLNodeRadius = a_radius * 2.0 * u_correctionRatio / u_sizeRatio;
  float webGLArrowHeadLength = webGLThickness * u_lengthToThicknessRatio * 2.0;
  float webGLArrowHeadThickness = webGLThickness * u_widenessToThicknessRatio;

  float da = a_barycentric.x;
  float db = a_barycentric.y;
  float dc = a_barycentric.z;

  vec2 delta = vec2(
      da * (webGLNodeRadius * unitNormal.y)
    + db * ((webGLNodeRadius + webGLArrowHeadLength) * unitNormal.y + webGLArrowHeadThickness * unitNormal.x)
    + dc * ((webGLNodeRadius + webGLArrowHeadLength) * unitNormal.y - webGLArrowHeadThickness * unitNormal.x),

      da * (-webGLNodeRadius * unitNormal.x)
    + db * (-(webGLNodeRadius + webGLArrowHeadLength) * unitNormal.x + webGLArrowHeadThickness * unitNormal.y)
    + dc * (-(webGLNodeRadius + webGLArrowHeadLength) * unitNormal.x - webGLArrowHeadThickness * unitNormal.y)
  );

  vec2 position = (u_matrix * vec3(a_position + delta, 1)).xy;

  gl_Position = vec4(position, 0, 1);

  #ifdef PICKING_MODE
  // For picking mode, we use the ID as the color:
  v_color = a_id;
  #else
  // For normal mode, we use the color:
  v_color = a_color;
  #endif

  v_color.a *= bias;
}
`, kw = _w, lg = WebGLRenderingContext, Xd = lg.UNSIGNED_BYTE, ns = lg.FLOAT, bw = [
    "u_matrix",
    "u_sizeRatio",
    "u_correctionRatio",
    "u_minEdgeThickness",
    "u_lengthToThicknessRatio",
    "u_widenessToThicknessRatio"
  ], Ea = {
    extremity: "target",
    lengthToThicknessRatio: 2.5,
    widenessToThicknessRatio: 2
  };
  function ug(e) {
    var t = te(te({}, Ea), {});
    return function(n) {
      function r() {
        return Ct(this, r), sn(this, r, arguments);
      }
      return an(r, n), Tt(r, [
        {
          key: "getDefinition",
          value: function() {
            return {
              VERTICES: 3,
              VERTEX_SHADER_SOURCE: kw,
              FRAGMENT_SHADER_SOURCE: Sw,
              METHOD: WebGLRenderingContext.TRIANGLES,
              UNIFORMS: bw,
              ATTRIBUTES: [
                {
                  name: "a_position",
                  size: 2,
                  type: ns
                },
                {
                  name: "a_normal",
                  size: 2,
                  type: ns
                },
                {
                  name: "a_radius",
                  size: 1,
                  type: ns
                },
                {
                  name: "a_color",
                  size: 4,
                  type: Xd,
                  normalized: true
                },
                {
                  name: "a_id",
                  size: 4,
                  type: Xd,
                  normalized: true
                }
              ],
              CONSTANT_ATTRIBUTES: [
                {
                  name: "a_barycentric",
                  size: 3,
                  type: ns
                }
              ],
              CONSTANT_DATA: [
                [
                  1,
                  0,
                  0
                ],
                [
                  0,
                  1,
                  0
                ],
                [
                  0,
                  0,
                  1
                ]
              ]
            };
          }
        },
        {
          key: "processVisibleItem",
          value: function(o, s, a, l, c) {
            if (t.extremity === "source") {
              var h = [
                l,
                a
              ];
              a = h[0], l = h[1];
            }
            var f = c.size || 1, p = l.size || 1, y = a.x, k = a.y, b = l.x, I = l.y, _ = _i(c.color), m = b - y, v = I - k, E = m * m + v * v, A = 0, F = 0;
            E && (E = 1 / Math.sqrt(E), A = -v * E * f, F = m * E * f);
            var R = this.array;
            R[s++] = b, R[s++] = I, R[s++] = -A, R[s++] = -F, R[s++] = p, R[s++] = _, R[s++] = o;
          }
        },
        {
          key: "setUniforms",
          value: function(o, s) {
            var a = s.gl, l = s.uniformLocations, c = l.u_matrix, h = l.u_sizeRatio, f = l.u_correctionRatio, p = l.u_minEdgeThickness, y = l.u_lengthToThicknessRatio, k = l.u_widenessToThicknessRatio;
            a.uniformMatrix3fv(c, false, o.matrix), a.uniform1f(h, o.sizeRatio), a.uniform1f(f, o.correctionRatio), a.uniform1f(p, o.minEdgeThickness), a.uniform1f(y, t.lengthToThicknessRatio), a.uniform1f(k, t.widenessToThicknessRatio);
          }
        }
      ]);
    }(ya);
  }
  ug();
  var xw = `
precision mediump float;

varying vec4 v_color;
varying vec2 v_normal;
varying float v_thickness;
varying float v_feather;

const vec4 transparent = vec4(0.0, 0.0, 0.0, 0.0);

void main(void) {
  // We only handle antialiasing for normal mode:
  #ifdef PICKING_MODE
  gl_FragColor = v_color;
  #else
  float dist = length(v_normal) * v_thickness;

  float t = smoothstep(
    v_thickness - v_feather,
    v_thickness,
    dist
  );

  gl_FragColor = mix(v_color, transparent, t);
  #endif
}
`, cg = xw, Cw = `
attribute vec4 a_id;
attribute vec4 a_color;
attribute vec2 a_normal;
attribute float a_normalCoef;
attribute vec2 a_positionStart;
attribute vec2 a_positionEnd;
attribute float a_positionCoef;
attribute float a_radius;
attribute float a_radiusCoef;

uniform mat3 u_matrix;
uniform float u_zoomRatio;
uniform float u_sizeRatio;
uniform float u_pixelRatio;
uniform float u_correctionRatio;
uniform float u_minEdgeThickness;
uniform float u_lengthToThicknessRatio;
uniform float u_feather;

varying vec4 v_color;
varying vec2 v_normal;
varying float v_thickness;
varying float v_feather;

const float bias = 255.0 / 254.0;

void main() {
  float minThickness = u_minEdgeThickness;

  float radius = a_radius * a_radiusCoef;
  vec2 normal = a_normal * a_normalCoef;
  vec2 position = a_positionStart * (1.0 - a_positionCoef) + a_positionEnd * a_positionCoef;

  float normalLength = length(normal);
  vec2 unitNormal = normal / normalLength;

  // These first computations are taken from edge.vert.glsl. Please read it to
  // get better comments on what's happening:
  float pixelsThickness = max(normalLength, minThickness * u_sizeRatio);
  float webGLThickness = pixelsThickness * u_correctionRatio / u_sizeRatio;

  // Here, we move the point to leave space for the arrow head:
  float direction = sign(radius);
  float webGLNodeRadius = direction * radius * 2.0 * u_correctionRatio / u_sizeRatio;
  float webGLArrowHeadLength = webGLThickness * u_lengthToThicknessRatio * 2.0;

  vec2 compensationVector = vec2(-direction * unitNormal.y, direction * unitNormal.x) * (webGLNodeRadius + webGLArrowHeadLength);

  // Here is the proper position of the vertex
  gl_Position = vec4((u_matrix * vec3(position + unitNormal * webGLThickness + compensationVector, 1)).xy, 0, 1);

  v_thickness = webGLThickness / u_zoomRatio;

  v_normal = unitNormal;

  v_feather = u_feather * u_correctionRatio / u_zoomRatio / u_pixelRatio * 2.0;

  #ifdef PICKING_MODE
  // For picking mode, we use the ID as the color:
  v_color = a_id;
  #else
  // For normal mode, we use the color:
  v_color = a_color;
  #endif

  v_color.a *= bias;
}
`, Tw = Cw, dg = WebGLRenderingContext, Zd = dg.UNSIGNED_BYTE, _r = dg.FLOAT, Rw = [
    "u_matrix",
    "u_zoomRatio",
    "u_sizeRatio",
    "u_correctionRatio",
    "u_pixelRatio",
    "u_feather",
    "u_minEdgeThickness",
    "u_lengthToThicknessRatio"
  ], Aw = {
    lengthToThicknessRatio: Ea.lengthToThicknessRatio
  };
  function fg(e) {
    var t = te(te({}, Aw), {});
    return function(n) {
      function r() {
        return Ct(this, r), sn(this, r, arguments);
      }
      return an(r, n), Tt(r, [
        {
          key: "getDefinition",
          value: function() {
            return {
              VERTICES: 6,
              VERTEX_SHADER_SOURCE: Tw,
              FRAGMENT_SHADER_SOURCE: cg,
              METHOD: WebGLRenderingContext.TRIANGLES,
              UNIFORMS: Rw,
              ATTRIBUTES: [
                {
                  name: "a_positionStart",
                  size: 2,
                  type: _r
                },
                {
                  name: "a_positionEnd",
                  size: 2,
                  type: _r
                },
                {
                  name: "a_normal",
                  size: 2,
                  type: _r
                },
                {
                  name: "a_color",
                  size: 4,
                  type: Zd,
                  normalized: true
                },
                {
                  name: "a_id",
                  size: 4,
                  type: Zd,
                  normalized: true
                },
                {
                  name: "a_radius",
                  size: 1,
                  type: _r
                }
              ],
              CONSTANT_ATTRIBUTES: [
                {
                  name: "a_positionCoef",
                  size: 1,
                  type: _r
                },
                {
                  name: "a_normalCoef",
                  size: 1,
                  type: _r
                },
                {
                  name: "a_radiusCoef",
                  size: 1,
                  type: _r
                }
              ],
              CONSTANT_DATA: [
                [
                  0,
                  1,
                  0
                ],
                [
                  0,
                  -1,
                  0
                ],
                [
                  1,
                  1,
                  1
                ],
                [
                  1,
                  1,
                  1
                ],
                [
                  0,
                  -1,
                  0
                ],
                [
                  1,
                  -1,
                  -1
                ]
              ]
            };
          }
        },
        {
          key: "processVisibleItem",
          value: function(o, s, a, l, c) {
            var h = c.size || 1, f = a.x, p = a.y, y = l.x, k = l.y, b = _i(c.color), I = y - f, _ = k - p, m = l.size || 1, v = I * I + _ * _, E = 0, A = 0;
            v && (v = 1 / Math.sqrt(v), E = -_ * v * h, A = I * v * h);
            var F = this.array;
            F[s++] = f, F[s++] = p, F[s++] = y, F[s++] = k, F[s++] = E, F[s++] = A, F[s++] = b, F[s++] = o, F[s++] = m;
          }
        },
        {
          key: "setUniforms",
          value: function(o, s) {
            var a = s.gl, l = s.uniformLocations, c = l.u_matrix, h = l.u_zoomRatio, f = l.u_feather, p = l.u_pixelRatio, y = l.u_correctionRatio, k = l.u_sizeRatio, b = l.u_minEdgeThickness, I = l.u_lengthToThicknessRatio;
            a.uniformMatrix3fv(c, false, o.matrix), a.uniform1f(h, o.zoomRatio), a.uniform1f(k, o.sizeRatio), a.uniform1f(y, o.correctionRatio), a.uniform1f(p, o.pixelRatio), a.uniform1f(f, o.antiAliasingFeather), a.uniform1f(b, o.minEdgeThickness), a.uniform1f(I, t.lengthToThicknessRatio);
          }
        }
      ]);
    }(ya);
  }
  fg();
  function Lw(e) {
    return fw([
      fg(),
      ug()
    ]);
  }
  var Iw = Lw(), Dw = Iw, Pw = `
attribute vec4 a_id;
attribute vec4 a_color;
attribute vec2 a_normal;
attribute float a_normalCoef;
attribute vec2 a_positionStart;
attribute vec2 a_positionEnd;
attribute float a_positionCoef;

uniform mat3 u_matrix;
uniform float u_sizeRatio;
uniform float u_zoomRatio;
uniform float u_pixelRatio;
uniform float u_correctionRatio;
uniform float u_minEdgeThickness;
uniform float u_feather;

varying vec4 v_color;
varying vec2 v_normal;
varying float v_thickness;
varying float v_feather;

const float bias = 255.0 / 254.0;

void main() {
  float minThickness = u_minEdgeThickness;

  vec2 normal = a_normal * a_normalCoef;
  vec2 position = a_positionStart * (1.0 - a_positionCoef) + a_positionEnd * a_positionCoef;

  float normalLength = length(normal);
  vec2 unitNormal = normal / normalLength;

  // We require edges to be at least "minThickness" pixels thick *on screen*
  // (so we need to compensate the size ratio):
  float pixelsThickness = max(normalLength, minThickness * u_sizeRatio);

  // Then, we need to retrieve the normalized thickness of the edge in the WebGL
  // referential (in a ([0, 1], [0, 1]) space), using our "magic" correction
  // ratio:
  float webGLThickness = pixelsThickness * u_correctionRatio / u_sizeRatio;

  // Here is the proper position of the vertex
  gl_Position = vec4((u_matrix * vec3(position + unitNormal * webGLThickness, 1)).xy, 0, 1);

  // For the fragment shader though, we need a thickness that takes the "magic"
  // correction ratio into account (as in webGLThickness), but so that the
  // antialiasing effect does not depend on the zoom level. So here's yet
  // another thickness version:
  v_thickness = webGLThickness / u_zoomRatio;

  v_normal = unitNormal;

  v_feather = u_feather * u_correctionRatio / u_zoomRatio / u_pixelRatio * 2.0;

  #ifdef PICKING_MODE
  // For picking mode, we use the ID as the color:
  v_color = a_id;
  #else
  // For normal mode, we use the color:
  v_color = a_color;
  #endif

  v_color.a *= bias;
}
`, Nw = Pw, hg = WebGLRenderingContext, qd = hg.UNSIGNED_BYTE, Oi = hg.FLOAT, Fw = [
    "u_matrix",
    "u_zoomRatio",
    "u_sizeRatio",
    "u_correctionRatio",
    "u_pixelRatio",
    "u_feather",
    "u_minEdgeThickness"
  ], zw = function(e) {
    function t() {
      return Ct(this, t), sn(this, t, arguments);
    }
    return an(t, e), Tt(t, [
      {
        key: "getDefinition",
        value: function() {
          return {
            VERTICES: 6,
            VERTEX_SHADER_SOURCE: Nw,
            FRAGMENT_SHADER_SOURCE: cg,
            METHOD: WebGLRenderingContext.TRIANGLES,
            UNIFORMS: Fw,
            ATTRIBUTES: [
              {
                name: "a_positionStart",
                size: 2,
                type: Oi
              },
              {
                name: "a_positionEnd",
                size: 2,
                type: Oi
              },
              {
                name: "a_normal",
                size: 2,
                type: Oi
              },
              {
                name: "a_color",
                size: 4,
                type: qd,
                normalized: true
              },
              {
                name: "a_id",
                size: 4,
                type: qd,
                normalized: true
              }
            ],
            CONSTANT_ATTRIBUTES: [
              {
                name: "a_positionCoef",
                size: 1,
                type: Oi
              },
              {
                name: "a_normalCoef",
                size: 1,
                type: Oi
              }
            ],
            CONSTANT_DATA: [
              [
                0,
                1
              ],
              [
                0,
                -1
              ],
              [
                1,
                1
              ],
              [
                1,
                1
              ],
              [
                0,
                -1
              ],
              [
                1,
                -1
              ]
            ]
          };
        }
      },
      {
        key: "processVisibleItem",
        value: function(r, i, o, s, a) {
          var l = a.size || 1, c = o.x, h = o.y, f = s.x, p = s.y, y = _i(a.color), k = f - c, b = p - h, I = k * k + b * b, _ = 0, m = 0;
          I && (I = 1 / Math.sqrt(I), _ = -b * I * l, m = k * I * l);
          var v = this.array;
          v[i++] = c, v[i++] = h, v[i++] = f, v[i++] = p, v[i++] = _, v[i++] = m, v[i++] = y, v[i++] = r;
        }
      },
      {
        key: "setUniforms",
        value: function(r, i) {
          var o = i.gl, s = i.uniformLocations, a = s.u_matrix, l = s.u_zoomRatio, c = s.u_feather, h = s.u_pixelRatio, f = s.u_correctionRatio, p = s.u_sizeRatio, y = s.u_minEdgeThickness;
          o.uniformMatrix3fv(a, false, r.matrix), o.uniform1f(l, r.zoomRatio), o.uniform1f(p, r.sizeRatio), o.uniform1f(f, r.correctionRatio), o.uniform1f(h, r.pixelRatio), o.uniform1f(c, r.antiAliasingFeather), o.uniform1f(y, r.minEdgeThickness);
        }
      }
    ]);
  }(ya), hc = {
    exports: {}
  }, li = typeof Reflect == "object" ? Reflect : null, Jd = li && typeof li.apply == "function" ? li.apply : function(t, n, r) {
    return Function.prototype.apply.call(t, n, r);
  }, _s;
  li && typeof li.ownKeys == "function" ? _s = li.ownKeys : Object.getOwnPropertySymbols ? _s = function(t) {
    return Object.getOwnPropertyNames(t).concat(Object.getOwnPropertySymbols(t));
  } : _s = function(t) {
    return Object.getOwnPropertyNames(t);
  };
  function Ow(e) {
    console && console.warn && console.warn(e);
  }
  var pg = Number.isNaN || function(t) {
    return t !== t;
  };
  function Ne() {
    Ne.init.call(this);
  }
  hc.exports = Ne;
  hc.exports.once = Mw;
  Ne.EventEmitter = Ne;
  Ne.prototype._events = void 0;
  Ne.prototype._eventsCount = 0;
  Ne.prototype._maxListeners = void 0;
  var ef = 10;
  function Sa(e) {
    if (typeof e != "function") throw new TypeError('The "listener" argument must be of type Function. Received type ' + typeof e);
  }
  Object.defineProperty(Ne, "defaultMaxListeners", {
    enumerable: true,
    get: function() {
      return ef;
    },
    set: function(e) {
      if (typeof e != "number" || e < 0 || pg(e)) throw new RangeError('The value of "defaultMaxListeners" is out of range. It must be a non-negative number. Received ' + e + ".");
      ef = e;
    }
  });
  Ne.init = function() {
    (this._events === void 0 || this._events === Object.getPrototypeOf(this)._events) && (this._events = /* @__PURE__ */ Object.create(null), this._eventsCount = 0), this._maxListeners = this._maxListeners || void 0;
  };
  Ne.prototype.setMaxListeners = function(t) {
    if (typeof t != "number" || t < 0 || pg(t)) throw new RangeError('The value of "n" is out of range. It must be a non-negative number. Received ' + t + ".");
    return this._maxListeners = t, this;
  };
  function gg(e) {
    return e._maxListeners === void 0 ? Ne.defaultMaxListeners : e._maxListeners;
  }
  Ne.prototype.getMaxListeners = function() {
    return gg(this);
  };
  Ne.prototype.emit = function(t) {
    for (var n = [], r = 1; r < arguments.length; r++) n.push(arguments[r]);
    var i = t === "error", o = this._events;
    if (o !== void 0) i = i && o.error === void 0;
    else if (!i) return false;
    if (i) {
      var s;
      if (n.length > 0 && (s = n[0]), s instanceof Error) throw s;
      var a = new Error("Unhandled error." + (s ? " (" + s.message + ")" : ""));
      throw a.context = s, a;
    }
    var l = o[t];
    if (l === void 0) return false;
    if (typeof l == "function") Jd(l, this, n);
    else for (var c = l.length, h = Eg(l, c), r = 0; r < c; ++r) Jd(h[r], this, n);
    return true;
  };
  function mg(e, t, n, r) {
    var i, o, s;
    if (Sa(n), o = e._events, o === void 0 ? (o = e._events = /* @__PURE__ */ Object.create(null), e._eventsCount = 0) : (o.newListener !== void 0 && (e.emit("newListener", t, n.listener ? n.listener : n), o = e._events), s = o[t]), s === void 0) s = o[t] = n, ++e._eventsCount;
    else if (typeof s == "function" ? s = o[t] = r ? [
      n,
      s
    ] : [
      s,
      n
    ] : r ? s.unshift(n) : s.push(n), i = gg(e), i > 0 && s.length > i && !s.warned) {
      s.warned = true;
      var a = new Error("Possible EventEmitter memory leak detected. " + s.length + " " + String(t) + " listeners added. Use emitter.setMaxListeners() to increase limit");
      a.name = "MaxListenersExceededWarning", a.emitter = e, a.type = t, a.count = s.length, Ow(a);
    }
    return e;
  }
  Ne.prototype.addListener = function(t, n) {
    return mg(this, t, n, false);
  };
  Ne.prototype.on = Ne.prototype.addListener;
  Ne.prototype.prependListener = function(t, n) {
    return mg(this, t, n, true);
  };
  function Gw() {
    if (!this.fired) return this.target.removeListener(this.type, this.wrapFn), this.fired = true, arguments.length === 0 ? this.listener.call(this.target) : this.listener.apply(this.target, arguments);
  }
  function vg(e, t, n) {
    var r = {
      fired: false,
      wrapFn: void 0,
      target: e,
      type: t,
      listener: n
    }, i = Gw.bind(r);
    return i.listener = n, r.wrapFn = i, i;
  }
  Ne.prototype.once = function(t, n) {
    return Sa(n), this.on(t, vg(this, t, n)), this;
  };
  Ne.prototype.prependOnceListener = function(t, n) {
    return Sa(n), this.prependListener(t, vg(this, t, n)), this;
  };
  Ne.prototype.removeListener = function(t, n) {
    var r, i, o, s, a;
    if (Sa(n), i = this._events, i === void 0) return this;
    if (r = i[t], r === void 0) return this;
    if (r === n || r.listener === n) --this._eventsCount === 0 ? this._events = /* @__PURE__ */ Object.create(null) : (delete i[t], i.removeListener && this.emit("removeListener", t, r.listener || n));
    else if (typeof r != "function") {
      for (o = -1, s = r.length - 1; s >= 0; s--) if (r[s] === n || r[s].listener === n) {
        a = r[s].listener, o = s;
        break;
      }
      if (o < 0) return this;
      o === 0 ? r.shift() : Uw(r, o), r.length === 1 && (i[t] = r[0]), i.removeListener !== void 0 && this.emit("removeListener", t, a || n);
    }
    return this;
  };
  Ne.prototype.off = Ne.prototype.removeListener;
  Ne.prototype.removeAllListeners = function(t) {
    var n, r, i;
    if (r = this._events, r === void 0) return this;
    if (r.removeListener === void 0) return arguments.length === 0 ? (this._events = /* @__PURE__ */ Object.create(null), this._eventsCount = 0) : r[t] !== void 0 && (--this._eventsCount === 0 ? this._events = /* @__PURE__ */ Object.create(null) : delete r[t]), this;
    if (arguments.length === 0) {
      var o = Object.keys(r), s;
      for (i = 0; i < o.length; ++i) s = o[i], s !== "removeListener" && this.removeAllListeners(s);
      return this.removeAllListeners("removeListener"), this._events = /* @__PURE__ */ Object.create(null), this._eventsCount = 0, this;
    }
    if (n = r[t], typeof n == "function") this.removeListener(t, n);
    else if (n !== void 0) for (i = n.length - 1; i >= 0; i--) this.removeListener(t, n[i]);
    return this;
  };
  function yg(e, t, n) {
    var r = e._events;
    if (r === void 0) return [];
    var i = r[t];
    return i === void 0 ? [] : typeof i == "function" ? n ? [
      i.listener || i
    ] : [
      i
    ] : n ? Bw(i) : Eg(i, i.length);
  }
  Ne.prototype.listeners = function(t) {
    return yg(this, t, true);
  };
  Ne.prototype.rawListeners = function(t) {
    return yg(this, t, false);
  };
  Ne.listenerCount = function(e, t) {
    return typeof e.listenerCount == "function" ? e.listenerCount(t) : wg.call(e, t);
  };
  Ne.prototype.listenerCount = wg;
  function wg(e) {
    var t = this._events;
    if (t !== void 0) {
      var n = t[e];
      if (typeof n == "function") return 1;
      if (n !== void 0) return n.length;
    }
    return 0;
  }
  Ne.prototype.eventNames = function() {
    return this._eventsCount > 0 ? _s(this._events) : [];
  };
  function Eg(e, t) {
    for (var n = new Array(t), r = 0; r < t; ++r) n[r] = e[r];
    return n;
  }
  function Uw(e, t) {
    for (; t + 1 < e.length; t++) e[t] = e[t + 1];
    e.pop();
  }
  function Bw(e) {
    for (var t = new Array(e.length), n = 0; n < t.length; ++n) t[n] = e[n].listener || e[n];
    return t;
  }
  function Mw(e, t) {
    return new Promise(function(n, r) {
      function i(s) {
        e.removeListener(t, o), r(s);
      }
      function o() {
        typeof e.removeListener == "function" && e.removeListener("error", i), n([].slice.call(arguments));
      }
      Sg(e, t, o, {
        once: true
      }), t !== "error" && $w(e, i, {
        once: true
      });
    });
  }
  function $w(e, t, n) {
    typeof e.on == "function" && Sg(e, "error", t, n);
  }
  function Sg(e, t, n, r) {
    if (typeof e.on == "function") r.once ? e.once(t, n) : e.on(t, n);
    else if (typeof e.addEventListener == "function") e.addEventListener(t, function i(o) {
      r.once && e.removeEventListener(t, i), n(o);
    });
    else throw new TypeError('The "emitter" argument must be of type EventEmitter. Received type ' + typeof e);
  }
  var _g = hc.exports, pc = function(e) {
    function t() {
      var n;
      return Ct(this, t), n = sn(this, t), n.rawEmitter = n, n;
    }
    return an(t, e), Tt(t);
  }(_g.EventEmitter), _a = function(t) {
    return t !== null && typeof t == "object" && typeof t.addUndirectedEdgeWithKey == "function" && typeof t.dropNode == "function" && typeof t.multi == "boolean";
  };
  const jw = To(_a);
  var Hw = function(t) {
    return t;
  }, Ww = function(t) {
    return t * t;
  }, Vw = function(t) {
    return t * (2 - t);
  }, Kw = function(t) {
    return (t *= 2) < 1 ? 0.5 * t * t : -0.5 * (--t * (t - 2) - 1);
  }, Yw = function(t) {
    return t * t * t;
  }, Qw = function(t) {
    return --t * t * t + 1;
  }, Xw = function(t) {
    return (t *= 2) < 1 ? 0.5 * t * t * t : 0.5 * ((t -= 2) * t * t + 2);
  }, Zw = {
    linear: Hw,
    quadraticIn: Ww,
    quadraticOut: Vw,
    quadraticInOut: Kw,
    cubicIn: Yw,
    cubicOut: Qw,
    cubicInOut: Xw
  }, qw = {
    easing: "quadraticInOut",
    duration: 150
  };
  function pn() {
    return Float32Array.of(1, 0, 0, 0, 1, 0, 0, 0, 1);
  }
  function rs(e, t, n) {
    return e[0] = t, e[4] = typeof n == "number" ? n : t, e;
  }
  function tf(e, t) {
    var n = Math.sin(t), r = Math.cos(t);
    return e[0] = r, e[1] = n, e[3] = -n, e[4] = r, e;
  }
  function nf(e, t, n) {
    return e[6] = t, e[7] = n, e;
  }
  function Jn(e, t) {
    var n = e[0], r = e[1], i = e[2], o = e[3], s = e[4], a = e[5], l = e[6], c = e[7], h = e[8], f = t[0], p = t[1], y = t[2], k = t[3], b = t[4], I = t[5], _ = t[6], m = t[7], v = t[8];
    return e[0] = f * n + p * o + y * l, e[1] = f * r + p * s + y * c, e[2] = f * i + p * a + y * h, e[3] = k * n + b * o + I * l, e[4] = k * r + b * s + I * c, e[5] = k * i + b * a + I * h, e[6] = _ * n + m * o + v * l, e[7] = _ * r + m * s + v * c, e[8] = _ * i + m * a + v * h, e;
  }
  function fu(e, t) {
    var n = arguments.length > 2 && arguments[2] !== void 0 ? arguments[2] : 1, r = e[0], i = e[1], o = e[3], s = e[4], a = e[6], l = e[7], c = t.x, h = t.y;
    return {
      x: c * r + h * o + a * n,
      y: c * i + h * s + l * n
    };
  }
  function Jw(e, t) {
    var n = e.height / e.width, r = t.height / t.width;
    return n < 1 && r > 1 || n > 1 && r < 1 ? 1 : Math.min(Math.max(r, 1 / r), Math.max(1 / n, n));
  }
  function Gi(e, t, n, r, i) {
    var o = e.angle, s = e.ratio, a = e.x, l = e.y, c = t.width, h = t.height, f = pn(), p = Math.min(c, h) - 2 * r, y = Jw(t, n);
    return i ? (Jn(f, nf(pn(), a, l)), Jn(f, rs(pn(), s)), Jn(f, tf(pn(), o)), Jn(f, rs(pn(), c / p / 2 / y, h / p / 2 / y))) : (Jn(f, rs(pn(), 2 * (p / c) * y, 2 * (p / h) * y)), Jn(f, tf(pn(), -o)), Jn(f, rs(pn(), 1 / s)), Jn(f, nf(pn(), -a, -l))), f;
  }
  function eE(e, t, n) {
    var r = fu(e, {
      x: Math.cos(t.angle),
      y: Math.sin(t.angle)
    }, 0), i = r.x, o = r.y;
    return 1 / Math.sqrt(Math.pow(i, 2) + Math.pow(o, 2)) / n.width;
  }
  function tE(e) {
    if (!e.order) return {
      x: [
        0,
        1
      ],
      y: [
        0,
        1
      ]
    };
    var t = 1 / 0, n = -1 / 0, r = 1 / 0, i = -1 / 0;
    return e.forEachNode(function(o, s) {
      var a = s.x, l = s.y;
      a < t && (t = a), a > n && (n = a), l < r && (r = l), l > i && (i = l);
    }), {
      x: [
        t,
        n
      ],
      y: [
        r,
        i
      ]
    };
  }
  function nE(e) {
    if (!jw(e)) throw new Error("Sigma: invalid graph instance.");
    e.forEachNode(function(t, n) {
      if (!Number.isFinite(n.x) || !Number.isFinite(n.y)) throw new Error("Sigma: Coordinates of node ".concat(t, " are invalid. A node must have a numeric 'x' and 'y' attribute."));
    });
  }
  function rE(e, t, n) {
    var r = document.createElement(e);
    if (t) for (var i in t) r.style[i] = t[i];
    if (n) for (var o in n) r.setAttribute(o, n[o]);
    return r;
  }
  function rf() {
    return typeof window.devicePixelRatio < "u" ? window.devicePixelRatio : 1;
  }
  function of(e, t, n) {
    return n.sort(function(r, i) {
      var o = t(r) || 0, s = t(i) || 0;
      return o < s ? -1 : o > s ? 1 : 0;
    });
  }
  function sf(e) {
    var t = vi(e.x, 2), n = t[0], r = t[1], i = vi(e.y, 2), o = i[0], s = i[1], a = Math.max(r - n, s - o), l = (r + n) / 2, c = (s + o) / 2;
    (a === 0 || Math.abs(a) === 1 / 0 || isNaN(a)) && (a = 1), isNaN(l) && (l = 0), isNaN(c) && (c = 0);
    var h = function(p) {
      return {
        x: 0.5 + (p.x - l) / a,
        y: 0.5 + (p.y - c) / a
      };
    };
    return h.applyTo = function(f) {
      f.x = 0.5 + (f.x - l) / a, f.y = 0.5 + (f.y - c) / a;
    }, h.inverse = function(f) {
      return {
        x: l + a * (f.x - 0.5),
        y: c + a * (f.y - 0.5)
      };
    }, h.ratio = a, h;
  }
  function hu(e) {
    "@babel/helpers - typeof";
    return hu = typeof Symbol == "function" && typeof Symbol.iterator == "symbol" ? function(t) {
      return typeof t;
    } : function(t) {
      return t && typeof Symbol == "function" && t.constructor === Symbol && t !== Symbol.prototype ? "symbol" : typeof t;
    }, hu(e);
  }
  function af(e, t) {
    var n = t.size;
    if (n !== 0) {
      var r = e.length;
      e.length += n;
      var i = 0;
      t.forEach(function(o) {
        e[r + i] = o, i++;
      });
    }
  }
  function sl(e) {
    e = e || {};
    for (var t = 0, n = arguments.length <= 1 ? 0 : arguments.length - 1; t < n; t++) {
      var r = t + 1 < 1 || arguments.length <= t + 1 ? void 0 : arguments[t + 1];
      r && Object.assign(e, r);
    }
    return e;
  }
  var gc = {
    hideEdgesOnMove: false,
    hideLabelsOnMove: false,
    renderLabels: true,
    renderEdgeLabels: false,
    enableEdgeEvents: false,
    defaultNodeColor: "#999",
    defaultNodeType: "circle",
    defaultEdgeColor: "#ccc",
    defaultEdgeType: "line",
    labelFont: "Arial",
    labelSize: 14,
    labelWeight: "normal",
    labelColor: {
      color: "#000"
    },
    edgeLabelFont: "Arial",
    edgeLabelSize: 14,
    edgeLabelWeight: "normal",
    edgeLabelColor: {
      attribute: "color"
    },
    stagePadding: 30,
    defaultDrawEdgeLabel: hw,
    defaultDrawNodeLabel: sg,
    defaultDrawNodeHover: pw,
    minEdgeThickness: 1.7,
    antiAliasingFeather: 1,
    dragTimeout: 100,
    draggedEventsTolerance: 3,
    inertiaDuration: 200,
    inertiaRatio: 3,
    zoomDuration: 250,
    zoomingRatio: 1.7,
    doubleClickTimeout: 300,
    doubleClickZoomingRatio: 2.2,
    doubleClickZoomingDuration: 200,
    tapMoveTolerance: 10,
    zoomToSizeRatioFunction: Math.sqrt,
    itemSizesReference: "screen",
    autoRescale: true,
    autoCenter: true,
    labelDensity: 1,
    labelGridCellSize: 100,
    labelRenderedSizeThreshold: 6,
    nodeReducer: null,
    edgeReducer: null,
    zIndex: false,
    minCameraRatio: null,
    maxCameraRatio: null,
    enableCameraZooming: true,
    enableCameraPanning: true,
    enableCameraRotation: true,
    cameraPanBoundaries: null,
    allowInvalidContainer: false,
    nodeProgramClasses: {},
    nodeHoverProgramClasses: {},
    edgeProgramClasses: {}
  }, iE = {
    circle: wa
  }, oE = {
    arrow: Dw,
    line: zw
  };
  function al(e) {
    if (typeof e.labelDensity != "number" || e.labelDensity < 0) throw new Error("Settings: invalid `labelDensity`. Expecting a positive number.");
    var t = e.minCameraRatio, n = e.maxCameraRatio;
    if (typeof t == "number" && typeof n == "number" && n < t) throw new Error("Settings: invalid camera ratio boundaries. Expecting `maxCameraRatio` to be greater than `minCameraRatio`.");
  }
  function sE(e) {
    var t = sl({}, gc, e);
    return t.nodeProgramClasses = sl({}, iE, t.nodeProgramClasses), t.edgeProgramClasses = sl({}, oE, t.edgeProgramClasses), t;
  }
  var is = 1.5, lf = function(e) {
    function t() {
      var n;
      return Ct(this, t), n = sn(this, t), $(n, "x", 0.5), $(n, "y", 0.5), $(n, "angle", 0), $(n, "ratio", 1), $(n, "minRatio", null), $(n, "maxRatio", null), $(n, "enabledZooming", true), $(n, "enabledPanning", true), $(n, "enabledRotation", true), $(n, "clean", null), $(n, "nextFrame", null), $(n, "previousState", null), $(n, "enabled", true), n.previousState = n.getState(), n;
    }
    return an(t, e), Tt(t, [
      {
        key: "enable",
        value: function() {
          return this.enabled = true, this;
        }
      },
      {
        key: "disable",
        value: function() {
          return this.enabled = false, this;
        }
      },
      {
        key: "getState",
        value: function() {
          return {
            x: this.x,
            y: this.y,
            angle: this.angle,
            ratio: this.ratio
          };
        }
      },
      {
        key: "hasState",
        value: function(r) {
          return this.x === r.x && this.y === r.y && this.ratio === r.ratio && this.angle === r.angle;
        }
      },
      {
        key: "getPreviousState",
        value: function() {
          var r = this.previousState;
          return r ? {
            x: r.x,
            y: r.y,
            angle: r.angle,
            ratio: r.ratio
          } : null;
        }
      },
      {
        key: "getBoundedRatio",
        value: function(r) {
          var i = r;
          return typeof this.minRatio == "number" && (i = Math.max(i, this.minRatio)), typeof this.maxRatio == "number" && (i = Math.min(i, this.maxRatio)), i;
        }
      },
      {
        key: "validateState",
        value: function(r) {
          var i = {};
          return this.enabledPanning && typeof r.x == "number" && (i.x = r.x), this.enabledPanning && typeof r.y == "number" && (i.y = r.y), this.enabledZooming && typeof r.ratio == "number" && (i.ratio = this.getBoundedRatio(r.ratio)), this.enabledRotation && typeof r.angle == "number" && (i.angle = r.angle), this.clean ? this.clean(te(te({}, this.getState()), i)) : i;
        }
      },
      {
        key: "isAnimated",
        value: function() {
          return !!this.nextFrame;
        }
      },
      {
        key: "setState",
        value: function(r) {
          if (!this.enabled) return this;
          this.previousState = this.getState();
          var i = this.validateState(r);
          return typeof i.x == "number" && (this.x = i.x), typeof i.y == "number" && (this.y = i.y), typeof i.ratio == "number" && (this.ratio = i.ratio), typeof i.angle == "number" && (this.angle = i.angle), this.hasState(this.previousState) || this.emit("updated", this.getState()), this;
        }
      },
      {
        key: "updateState",
        value: function(r) {
          return this.setState(r(this.getState())), this;
        }
      },
      {
        key: "animate",
        value: function(r) {
          var i = this, o = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : {}, s = arguments.length > 2 ? arguments[2] : void 0;
          if (!s) return new Promise(function(y) {
            return i.animate(r, o, y);
          });
          if (this.enabled) {
            var a = te(te({}, qw), o), l = this.validateState(r), c = typeof a.easing == "function" ? a.easing : Zw[a.easing], h = Date.now(), f = this.getState(), p = function() {
              var k = (Date.now() - h) / a.duration;
              if (k >= 1) {
                i.nextFrame = null, i.setState(l), i.animationCallback && (i.animationCallback.call(null), i.animationCallback = void 0);
                return;
              }
              var b = c(k), I = {};
              typeof l.x == "number" && (I.x = f.x + (l.x - f.x) * b), typeof l.y == "number" && (I.y = f.y + (l.y - f.y) * b), i.enabledRotation && typeof l.angle == "number" && (I.angle = f.angle + (l.angle - f.angle) * b), typeof l.ratio == "number" && (I.ratio = f.ratio + (l.ratio - f.ratio) * b), i.setState(I), i.nextFrame = requestAnimationFrame(p);
            };
            this.nextFrame ? (cancelAnimationFrame(this.nextFrame), this.animationCallback && this.animationCallback.call(null), this.nextFrame = requestAnimationFrame(p)) : p(), this.animationCallback = s;
          }
        }
      },
      {
        key: "animatedZoom",
        value: function(r) {
          return r ? typeof r == "number" ? this.animate({
            ratio: this.ratio / r
          }) : this.animate({
            ratio: this.ratio / (r.factor || is)
          }, r) : this.animate({
            ratio: this.ratio / is
          });
        }
      },
      {
        key: "animatedUnzoom",
        value: function(r) {
          return r ? typeof r == "number" ? this.animate({
            ratio: this.ratio * r
          }) : this.animate({
            ratio: this.ratio * (r.factor || is)
          }, r) : this.animate({
            ratio: this.ratio * is
          });
        }
      },
      {
        key: "animatedReset",
        value: function(r) {
          return this.animate({
            x: 0.5,
            y: 0.5,
            ratio: 1,
            angle: 0
          }, r);
        }
      },
      {
        key: "copy",
        value: function() {
          return t.from(this.getState());
        }
      }
    ], [
      {
        key: "from",
        value: function(r) {
          var i = new t();
          return i.setState(r);
        }
      }
    ]);
  }(pc);
  function yn(e, t) {
    var n = t.getBoundingClientRect();
    return {
      x: e.clientX - n.left,
      y: e.clientY - n.top
    };
  }
  function zn(e, t) {
    var n = te(te({}, yn(e, t)), {}, {
      sigmaDefaultPrevented: false,
      preventSigmaDefault: function() {
        n.sigmaDefaultPrevented = true;
      },
      original: e
    });
    return n;
  }
  function Ui(e) {
    var t = "x" in e ? e : te(te({}, e.touches[0] || e.previousTouches[0]), {}, {
      original: e.original,
      sigmaDefaultPrevented: e.sigmaDefaultPrevented,
      preventSigmaDefault: function() {
        e.sigmaDefaultPrevented = true, t.sigmaDefaultPrevented = true;
      }
    });
    return t;
  }
  function aE(e, t) {
    return te(te({}, zn(e, t)), {}, {
      delta: kg(e)
    });
  }
  var lE = 2;
  function ks(e) {
    for (var t = [], n = 0, r = Math.min(e.length, lE); n < r; n++) t.push(e[n]);
    return t;
  }
  function Bi(e, t, n) {
    var r = {
      touches: ks(e.touches).map(function(i) {
        return yn(i, n);
      }),
      previousTouches: t.map(function(i) {
        return yn(i, n);
      }),
      sigmaDefaultPrevented: false,
      preventSigmaDefault: function() {
        r.sigmaDefaultPrevented = true;
      },
      original: e
    };
    return r;
  }
  function kg(e) {
    if (typeof e.deltaY < "u") return e.deltaY * -3 / 360;
    if (typeof e.detail < "u") return e.detail / -9;
    throw new Error("Captor: could not extract delta from event.");
  }
  var bg = function(e) {
    function t(n, r) {
      var i;
      return Ct(this, t), i = sn(this, t), i.container = n, i.renderer = r, i;
    }
    return an(t, e), Tt(t);
  }(pc), uE = [
    "doubleClickTimeout",
    "doubleClickZoomingDuration",
    "doubleClickZoomingRatio",
    "dragTimeout",
    "draggedEventsTolerance",
    "inertiaDuration",
    "inertiaRatio",
    "zoomDuration",
    "zoomingRatio"
  ], cE = uE.reduce(function(e, t) {
    return te(te({}, e), {}, $({}, t, gc[t]));
  }, {}), dE = function(e) {
    function t(n, r) {
      var i;
      return Ct(this, t), i = sn(this, t, [
        n,
        r
      ]), $(i, "enabled", true), $(i, "draggedEvents", 0), $(i, "downStartTime", null), $(i, "lastMouseX", null), $(i, "lastMouseY", null), $(i, "isMouseDown", false), $(i, "isMoving", false), $(i, "movingTimeout", null), $(i, "startCameraState", null), $(i, "clicks", 0), $(i, "doubleClickTimeout", null), $(i, "currentWheelDirection", 0), $(i, "settings", cE), i.handleClick = i.handleClick.bind(i), i.handleRightClick = i.handleRightClick.bind(i), i.handleDown = i.handleDown.bind(i), i.handleUp = i.handleUp.bind(i), i.handleMove = i.handleMove.bind(i), i.handleWheel = i.handleWheel.bind(i), i.handleLeave = i.handleLeave.bind(i), i.handleEnter = i.handleEnter.bind(i), n.addEventListener("click", i.handleClick, {
        capture: false
      }), n.addEventListener("contextmenu", i.handleRightClick, {
        capture: false
      }), n.addEventListener("mousedown", i.handleDown, {
        capture: false
      }), n.addEventListener("wheel", i.handleWheel, {
        capture: false
      }), n.addEventListener("mouseleave", i.handleLeave, {
        capture: false
      }), n.addEventListener("mouseenter", i.handleEnter, {
        capture: false
      }), document.addEventListener("mousemove", i.handleMove, {
        capture: false
      }), document.addEventListener("mouseup", i.handleUp, {
        capture: false
      }), i;
    }
    return an(t, e), Tt(t, [
      {
        key: "kill",
        value: function() {
          var r = this.container;
          r.removeEventListener("click", this.handleClick), r.removeEventListener("contextmenu", this.handleRightClick), r.removeEventListener("mousedown", this.handleDown), r.removeEventListener("wheel", this.handleWheel), r.removeEventListener("mouseleave", this.handleLeave), r.removeEventListener("mouseenter", this.handleEnter), document.removeEventListener("mousemove", this.handleMove), document.removeEventListener("mouseup", this.handleUp);
        }
      },
      {
        key: "handleClick",
        value: function(r) {
          var i = this;
          if (this.enabled) {
            if (this.clicks++, this.clicks === 2) return this.clicks = 0, typeof this.doubleClickTimeout == "number" && (clearTimeout(this.doubleClickTimeout), this.doubleClickTimeout = null), this.handleDoubleClick(r);
            setTimeout(function() {
              i.clicks = 0, i.doubleClickTimeout = null;
            }, this.settings.doubleClickTimeout), this.draggedEvents < this.settings.draggedEventsTolerance && this.emit("click", zn(r, this.container));
          }
        }
      },
      {
        key: "handleRightClick",
        value: function(r) {
          this.enabled && this.emit("rightClick", zn(r, this.container));
        }
      },
      {
        key: "handleDoubleClick",
        value: function(r) {
          if (this.enabled) {
            r.preventDefault(), r.stopPropagation();
            var i = zn(r, this.container);
            if (this.emit("doubleClick", i), !i.sigmaDefaultPrevented) {
              var o = this.renderer.getCamera(), s = o.getBoundedRatio(o.getState().ratio / this.settings.doubleClickZoomingRatio);
              o.animate(this.renderer.getViewportZoomedState(yn(r, this.container), s), {
                easing: "quadraticInOut",
                duration: this.settings.doubleClickZoomingDuration
              });
            }
          }
        }
      },
      {
        key: "handleDown",
        value: function(r) {
          if (this.enabled) {
            if (r.button === 0) {
              this.startCameraState = this.renderer.getCamera().getState();
              var i = yn(r, this.container), o = i.x, s = i.y;
              this.lastMouseX = o, this.lastMouseY = s, this.draggedEvents = 0, this.downStartTime = Date.now(), this.isMouseDown = true;
            }
            this.emit("mousedown", zn(r, this.container));
          }
        }
      },
      {
        key: "handleUp",
        value: function(r) {
          var i = this;
          if (!(!this.enabled || !this.isMouseDown)) {
            var o = this.renderer.getCamera();
            this.isMouseDown = false, typeof this.movingTimeout == "number" && (clearTimeout(this.movingTimeout), this.movingTimeout = null);
            var s = yn(r, this.container), a = s.x, l = s.y, c = o.getState(), h = o.getPreviousState() || {
              x: 0,
              y: 0
            };
            this.isMoving ? o.animate({
              x: c.x + this.settings.inertiaRatio * (c.x - h.x),
              y: c.y + this.settings.inertiaRatio * (c.y - h.y)
            }, {
              duration: this.settings.inertiaDuration,
              easing: "quadraticOut"
            }) : (this.lastMouseX !== a || this.lastMouseY !== l) && o.setState({
              x: c.x,
              y: c.y
            }), this.isMoving = false, setTimeout(function() {
              var f = i.draggedEvents > 0;
              i.draggedEvents = 0, f && i.renderer.getSetting("hideEdgesOnMove") && i.renderer.refresh();
            }, 0), this.emit("mouseup", zn(r, this.container));
          }
        }
      },
      {
        key: "handleMove",
        value: function(r) {
          var i = this;
          if (this.enabled) {
            var o = zn(r, this.container);
            if (this.emit("mousemovebody", o), (r.target === this.container || r.composedPath()[0] === this.container) && this.emit("mousemove", o), !o.sigmaDefaultPrevented && this.isMouseDown) {
              this.isMoving = true, this.draggedEvents++, typeof this.movingTimeout == "number" && clearTimeout(this.movingTimeout), this.movingTimeout = window.setTimeout(function() {
                i.movingTimeout = null, i.isMoving = false;
              }, this.settings.dragTimeout);
              var s = this.renderer.getCamera(), a = yn(r, this.container), l = a.x, c = a.y, h = this.renderer.viewportToFramedGraph({
                x: this.lastMouseX,
                y: this.lastMouseY
              }), f = this.renderer.viewportToFramedGraph({
                x: l,
                y: c
              }), p = h.x - f.x, y = h.y - f.y, k = s.getState(), b = k.x + p, I = k.y + y;
              s.setState({
                x: b,
                y: I
              }), this.lastMouseX = l, this.lastMouseY = c, r.preventDefault(), r.stopPropagation();
            }
          }
        }
      },
      {
        key: "handleLeave",
        value: function(r) {
          this.emit("mouseleave", zn(r, this.container));
        }
      },
      {
        key: "handleEnter",
        value: function(r) {
          this.emit("mouseenter", zn(r, this.container));
        }
      },
      {
        key: "handleWheel",
        value: function(r) {
          var i = this, o = this.renderer.getCamera();
          if (!(!this.enabled || !o.enabledZooming)) {
            var s = kg(r);
            if (s) {
              var a = aE(r, this.container);
              if (this.emit("wheel", a), a.sigmaDefaultPrevented) {
                r.preventDefault(), r.stopPropagation();
                return;
              }
              var l = o.getState().ratio, c = s > 0 ? 1 / this.settings.zoomingRatio : this.settings.zoomingRatio, h = o.getBoundedRatio(l * c), f = s > 0 ? 1 : -1, p = Date.now();
              l !== h && (r.preventDefault(), r.stopPropagation(), !(this.currentWheelDirection === f && this.lastWheelTriggerTime && p - this.lastWheelTriggerTime < this.settings.zoomDuration / 5) && (o.animate(this.renderer.getViewportZoomedState(yn(r, this.container), h), {
                easing: "quadraticOut",
                duration: this.settings.zoomDuration
              }, function() {
                i.currentWheelDirection = 0;
              }), this.currentWheelDirection = f, this.lastWheelTriggerTime = p));
            }
          }
        }
      },
      {
        key: "setSettings",
        value: function(r) {
          this.settings = r;
        }
      }
    ]);
  }(bg), fE = [
    "dragTimeout",
    "inertiaDuration",
    "inertiaRatio",
    "doubleClickTimeout",
    "doubleClickZoomingRatio",
    "doubleClickZoomingDuration",
    "tapMoveTolerance"
  ], hE = fE.reduce(function(e, t) {
    return te(te({}, e), {}, $({}, t, gc[t]));
  }, {}), pE = function(e) {
    function t(n, r) {
      var i;
      return Ct(this, t), i = sn(this, t, [
        n,
        r
      ]), $(i, "enabled", true), $(i, "isMoving", false), $(i, "hasMoved", false), $(i, "touchMode", 0), $(i, "startTouchesPositions", []), $(i, "lastTouches", []), $(i, "lastTap", null), $(i, "settings", hE), i.handleStart = i.handleStart.bind(i), i.handleLeave = i.handleLeave.bind(i), i.handleMove = i.handleMove.bind(i), n.addEventListener("touchstart", i.handleStart, {
        capture: false
      }), n.addEventListener("touchcancel", i.handleLeave, {
        capture: false
      }), document.addEventListener("touchend", i.handleLeave, {
        capture: false,
        passive: false
      }), document.addEventListener("touchmove", i.handleMove, {
        capture: false,
        passive: false
      }), i;
    }
    return an(t, e), Tt(t, [
      {
        key: "kill",
        value: function() {
          var r = this.container;
          r.removeEventListener("touchstart", this.handleStart), r.removeEventListener("touchcancel", this.handleLeave), document.removeEventListener("touchend", this.handleLeave), document.removeEventListener("touchmove", this.handleMove);
        }
      },
      {
        key: "getDimensions",
        value: function() {
          return {
            width: this.container.offsetWidth,
            height: this.container.offsetHeight
          };
        }
      },
      {
        key: "handleStart",
        value: function(r) {
          var i = this;
          if (this.enabled) {
            r.preventDefault();
            var o = ks(r.touches);
            if (this.touchMode = o.length, this.startCameraState = this.renderer.getCamera().getState(), this.startTouchesPositions = o.map(function(y) {
              return yn(y, i.container);
            }), this.touchMode === 2) {
              var s = vi(this.startTouchesPositions, 2), a = s[0], l = a.x, c = a.y, h = s[1], f = h.x, p = h.y;
              this.startTouchesAngle = Math.atan2(p - c, f - l), this.startTouchesDistance = Math.sqrt(Math.pow(f - l, 2) + Math.pow(p - c, 2));
            }
            this.emit("touchdown", Bi(r, this.lastTouches, this.container)), this.lastTouches = o, this.lastTouchesPositions = this.startTouchesPositions;
          }
        }
      },
      {
        key: "handleLeave",
        value: function(r) {
          if (!(!this.enabled || !this.startTouchesPositions.length)) {
            switch (r.cancelable && r.preventDefault(), this.movingTimeout && (this.isMoving = false, clearTimeout(this.movingTimeout)), this.touchMode) {
              case 2:
                if (r.touches.length === 1) {
                  this.handleStart(r), r.preventDefault();
                  break;
                }
              case 1:
                if (this.isMoving) {
                  var i = this.renderer.getCamera(), o = i.getState(), s = i.getPreviousState() || {
                    x: 0,
                    y: 0
                  };
                  i.animate({
                    x: o.x + this.settings.inertiaRatio * (o.x - s.x),
                    y: o.y + this.settings.inertiaRatio * (o.y - s.y)
                  }, {
                    duration: this.settings.inertiaDuration,
                    easing: "quadraticOut"
                  });
                }
                this.hasMoved = false, this.isMoving = false, this.touchMode = 0;
                break;
            }
            if (this.emit("touchup", Bi(r, this.lastTouches, this.container)), !r.touches.length) {
              var a = yn(this.lastTouches[0], this.container), l = this.startTouchesPositions[0], c = Math.pow(a.x - l.x, 2) + Math.pow(a.y - l.y, 2);
              if (!r.touches.length && c < Math.pow(this.settings.tapMoveTolerance, 2)) if (this.lastTap && Date.now() - this.lastTap.time < this.settings.doubleClickTimeout) {
                var h = Bi(r, this.lastTouches, this.container);
                if (this.emit("doubletap", h), this.lastTap = null, !h.sigmaDefaultPrevented) {
                  var f = this.renderer.getCamera(), p = f.getBoundedRatio(f.getState().ratio / this.settings.doubleClickZoomingRatio);
                  f.animate(this.renderer.getViewportZoomedState(a, p), {
                    easing: "quadraticInOut",
                    duration: this.settings.doubleClickZoomingDuration
                  });
                }
              } else {
                var y = Bi(r, this.lastTouches, this.container);
                this.emit("tap", y), this.lastTap = {
                  time: Date.now(),
                  position: y.touches[0] || y.previousTouches[0]
                };
              }
            }
            this.lastTouches = ks(r.touches), this.startTouchesPositions = [];
          }
        }
      },
      {
        key: "handleMove",
        value: function(r) {
          var i = this;
          if (!(!this.enabled || !this.startTouchesPositions.length)) {
            r.preventDefault();
            var o = ks(r.touches), s = o.map(function(D) {
              return yn(D, i.container);
            }), a = this.lastTouches;
            this.lastTouches = o, this.lastTouchesPositions = s;
            var l = Bi(r, a, this.container);
            if (this.emit("touchmove", l), !l.sigmaDefaultPrevented && (this.hasMoved || (this.hasMoved = s.some(function(D, x) {
              var Q = i.startTouchesPositions[x];
              return Q && (D.x !== Q.x || D.y !== Q.y);
            })), !!this.hasMoved)) {
              this.isMoving = true, this.movingTimeout && clearTimeout(this.movingTimeout), this.movingTimeout = window.setTimeout(function() {
                i.isMoving = false;
              }, this.settings.dragTimeout);
              var c = this.renderer.getCamera(), h = this.startCameraState, f = this.renderer.getSetting("stagePadding");
              switch (this.touchMode) {
                case 1: {
                  var p = this.renderer.viewportToFramedGraph((this.startTouchesPositions || [])[0]), y = p.x, k = p.y, b = this.renderer.viewportToFramedGraph(s[0]), I = b.x, _ = b.y;
                  c.setState({
                    x: h.x + y - I,
                    y: h.y + k - _
                  });
                  break;
                }
                case 2: {
                  var m = {
                    x: 0.5,
                    y: 0.5,
                    angle: 0,
                    ratio: 1
                  }, v = s[0], E = v.x, A = v.y, F = s[1], R = F.x, L = F.y, C = Math.atan2(L - A, R - E) - this.startTouchesAngle, N = Math.hypot(L - A, R - E) / this.startTouchesDistance, V = c.getBoundedRatio(h.ratio / N);
                  m.ratio = V, m.angle = h.angle + C;
                  var B = this.getDimensions(), K = this.renderer.viewportToFramedGraph((this.startTouchesPositions || [])[0], {
                    cameraState: h
                  }), O = Math.min(B.width, B.height) - 2 * f, re = O / B.width, ae = O / B.height, J = V / O, S = E - O / 2 / re, j = A - O / 2 / ae, H = [
                    S * Math.cos(-m.angle) - j * Math.sin(-m.angle),
                    j * Math.cos(-m.angle) + S * Math.sin(-m.angle)
                  ];
                  S = H[0], j = H[1], m.x = K.x - S * J, m.y = K.y + j * J, c.setState(m);
                  break;
                }
              }
            }
          }
        }
      },
      {
        key: "setSettings",
        value: function(r) {
          this.settings = r;
        }
      }
    ]);
  }(bg);
  function gE(e) {
    if (Array.isArray(e)) return cu(e);
  }
  function mE(e) {
    if (typeof Symbol < "u" && e[Symbol.iterator] != null || e["@@iterator"] != null) return Array.from(e);
  }
  function vE() {
    throw new TypeError(`Invalid attempt to spread non-iterable instance.
In order to be iterable, non-array objects must have a [Symbol.iterator]() method.`);
  }
  function uf(e) {
    return gE(e) || mE(e) || Jp(e) || vE();
  }
  function yE(e, t) {
    if (e == null) return {};
    var n = {};
    for (var r in e) if ({}.hasOwnProperty.call(e, r)) {
      if (t.indexOf(r) !== -1) continue;
      n[r] = e[r];
    }
    return n;
  }
  function ll(e, t) {
    if (e == null) return {};
    var n, r, i = yE(e, t);
    if (Object.getOwnPropertySymbols) {
      var o = Object.getOwnPropertySymbols(e);
      for (r = 0; r < o.length; r++) n = o[r], t.indexOf(n) === -1 && {}.propertyIsEnumerable.call(e, n) && (i[n] = e[n]);
    }
    return i;
  }
  var cf = function() {
    function e(t, n) {
      Ct(this, e), this.key = t, this.size = n;
    }
    return Tt(e, null, [
      {
        key: "compare",
        value: function(n, r) {
          return n.size > r.size ? -1 : n.size < r.size || n.key > r.key ? 1 : -1;
        }
      }
    ]);
  }(), df = function() {
    function e() {
      Ct(this, e), $(this, "width", 0), $(this, "height", 0), $(this, "cellSize", 0), $(this, "columns", 0), $(this, "rows", 0), $(this, "cells", {});
    }
    return Tt(e, [
      {
        key: "resizeAndClear",
        value: function(n, r) {
          this.width = n.width, this.height = n.height, this.cellSize = r, this.columns = Math.ceil(n.width / r), this.rows = Math.ceil(n.height / r), this.cells = {};
        }
      },
      {
        key: "getIndex",
        value: function(n) {
          var r = Math.floor(n.x / this.cellSize), i = Math.floor(n.y / this.cellSize);
          return i * this.columns + r;
        }
      },
      {
        key: "add",
        value: function(n, r, i) {
          var o = new cf(n, r), s = this.getIndex(i), a = this.cells[s];
          a || (a = [], this.cells[s] = a), a.push(o);
        }
      },
      {
        key: "organize",
        value: function() {
          for (var n in this.cells) {
            var r = this.cells[n];
            r.sort(cf.compare);
          }
        }
      },
      {
        key: "getLabelsToDisplay",
        value: function(n, r) {
          var i = this.cellSize * this.cellSize, o = i / n / n, s = o * r / i, a = Math.ceil(s), l = [];
          for (var c in this.cells) for (var h = this.cells[c], f = 0; f < Math.min(a, h.length); f++) l.push(h[f].key);
          return l;
        }
      }
    ]);
  }();
  function wE(e) {
    var t = e.graph, n = e.hoveredNode, r = e.highlightedNodes, i = e.displayedNodeLabels, o = [];
    return t.forEachEdge(function(s, a, l, c) {
      (l === n || c === n || r.has(l) || r.has(c) || i.has(l) && i.has(c)) && o.push(s);
    }), o;
  }
  var ff = 150, hf = 50, Un = Object.prototype.hasOwnProperty;
  function EE(e, t, n) {
    if (!Un.call(n, "x") || !Un.call(n, "y")) throw new Error('Sigma: could not find a valid position (x, y) for node "'.concat(t, '". All your nodes must have a number "x" and "y". Maybe your forgot to apply a layout or your "nodeReducer" is not returning the correct data?'));
    return n.color || (n.color = e.defaultNodeColor), !n.label && n.label !== "" && (n.label = null), n.label !== void 0 && n.label !== null ? n.label = "" + n.label : n.label = null, n.size || (n.size = 2), Un.call(n, "hidden") || (n.hidden = false), Un.call(n, "highlighted") || (n.highlighted = false), Un.call(n, "forceLabel") || (n.forceLabel = false), (!n.type || n.type === "") && (n.type = e.defaultNodeType), n.zIndex || (n.zIndex = 0), n;
  }
  function SE(e, t, n) {
    return n.color || (n.color = e.defaultEdgeColor), n.label || (n.label = ""), n.size || (n.size = 0.5), Un.call(n, "hidden") || (n.hidden = false), Un.call(n, "forceLabel") || (n.forceLabel = false), (!n.type || n.type === "") && (n.type = e.defaultEdgeType), n.zIndex || (n.zIndex = 0), n;
  }
  var _E = function(e) {
    function t(n, r) {
      var i, o = arguments.length > 2 && arguments[2] !== void 0 ? arguments[2] : {};
      if (Ct(this, t), i = sn(this, t), $(i, "elements", {}), $(i, "canvasContexts", {}), $(i, "webGLContexts", {}), $(i, "pickingLayers", /* @__PURE__ */ new Set()), $(i, "textures", {}), $(i, "frameBuffers", {}), $(i, "activeListeners", {}), $(i, "labelGrid", new df()), $(i, "nodeDataCache", {}), $(i, "edgeDataCache", {}), $(i, "nodeProgramIndex", {}), $(i, "edgeProgramIndex", {}), $(i, "nodesWithForcedLabels", /* @__PURE__ */ new Set()), $(i, "edgesWithForcedLabels", /* @__PURE__ */ new Set()), $(i, "nodeExtent", {
        x: [
          0,
          1
        ],
        y: [
          0,
          1
        ]
      }), $(i, "nodeZExtent", [
        1 / 0,
        -1 / 0
      ]), $(i, "edgeZExtent", [
        1 / 0,
        -1 / 0
      ]), $(i, "matrix", pn()), $(i, "invMatrix", pn()), $(i, "correctionRatio", 1), $(i, "customBBox", null), $(i, "normalizationFunction", sf({
        x: [
          0,
          1
        ],
        y: [
          0,
          1
        ]
      })), $(i, "graphToViewportRatio", 1), $(i, "itemIDsIndex", {}), $(i, "nodeIndices", {}), $(i, "edgeIndices", {}), $(i, "width", 0), $(i, "height", 0), $(i, "pixelRatio", rf()), $(i, "pickingDownSizingRatio", 2 * i.pixelRatio), $(i, "displayedNodeLabels", /* @__PURE__ */ new Set()), $(i, "displayedEdgeLabels", /* @__PURE__ */ new Set()), $(i, "highlightedNodes", /* @__PURE__ */ new Set()), $(i, "hoveredNode", null), $(i, "hoveredEdge", null), $(i, "renderFrame", null), $(i, "renderHighlightedNodesFrame", null), $(i, "needToProcess", false), $(i, "checkEdgesEventsFrame", null), $(i, "nodePrograms", {}), $(i, "nodeHoverPrograms", {}), $(i, "edgePrograms", {}), i.settings = sE(o), al(i.settings), nE(n), !(r instanceof HTMLElement)) throw new Error("Sigma: container should be an html element.");
      i.graph = n, i.container = r, i.createWebGLContext("edges", {
        picking: o.enableEdgeEvents
      }), i.createCanvasContext("edgeLabels"), i.createWebGLContext("nodes", {
        picking: true
      }), i.createCanvasContext("labels"), i.createCanvasContext("hovers"), i.createWebGLContext("hoverNodes"), i.createCanvasContext("mouse", {
        style: {
          touchAction: "none",
          userSelect: "none"
        }
      }), i.resize();
      for (var s in i.settings.nodeProgramClasses) i.registerNodeProgram(s, i.settings.nodeProgramClasses[s], i.settings.nodeHoverProgramClasses[s]);
      for (var a in i.settings.edgeProgramClasses) i.registerEdgeProgram(a, i.settings.edgeProgramClasses[a]);
      return i.camera = new lf(), i.bindCameraHandlers(), i.mouseCaptor = new dE(i.elements.mouse, i), i.mouseCaptor.setSettings(i.settings), i.touchCaptor = new pE(i.elements.mouse, i), i.touchCaptor.setSettings(i.settings), i.bindEventHandlers(), i.bindGraphHandlers(), i.handleSettingsUpdate(), i.refresh(), i;
    }
    return an(t, e), Tt(t, [
      {
        key: "registerNodeProgram",
        value: function(r, i, o) {
          return this.nodePrograms[r] && this.nodePrograms[r].kill(), this.nodeHoverPrograms[r] && this.nodeHoverPrograms[r].kill(), this.nodePrograms[r] = new i(this.webGLContexts.nodes, this.frameBuffers.nodes, this), this.nodeHoverPrograms[r] = new (o || i)(this.webGLContexts.hoverNodes, null, this), this;
        }
      },
      {
        key: "registerEdgeProgram",
        value: function(r, i) {
          return this.edgePrograms[r] && this.edgePrograms[r].kill(), this.edgePrograms[r] = new i(this.webGLContexts.edges, this.frameBuffers.edges, this), this;
        }
      },
      {
        key: "unregisterNodeProgram",
        value: function(r) {
          if (this.nodePrograms[r]) {
            var i = this.nodePrograms, o = i[r], s = ll(i, [
              r
            ].map(ao));
            o.kill(), this.nodePrograms = s;
          }
          if (this.nodeHoverPrograms[r]) {
            var a = this.nodeHoverPrograms, l = a[r], c = ll(a, [
              r
            ].map(ao));
            l.kill(), this.nodePrograms = c;
          }
          return this;
        }
      },
      {
        key: "unregisterEdgeProgram",
        value: function(r) {
          if (this.edgePrograms[r]) {
            var i = this.edgePrograms, o = i[r], s = ll(i, [
              r
            ].map(ao));
            o.kill(), this.edgePrograms = s;
          }
          return this;
        }
      },
      {
        key: "resetWebGLTexture",
        value: function(r) {
          var i = this.webGLContexts[r], o = this.frameBuffers[r], s = this.textures[r];
          s && i.deleteTexture(s);
          var a = i.createTexture();
          return i.bindFramebuffer(i.FRAMEBUFFER, o), i.bindTexture(i.TEXTURE_2D, a), i.texImage2D(i.TEXTURE_2D, 0, i.RGBA, this.width, this.height, 0, i.RGBA, i.UNSIGNED_BYTE, null), i.framebufferTexture2D(i.FRAMEBUFFER, i.COLOR_ATTACHMENT0, i.TEXTURE_2D, a, 0), this.textures[r] = a, this;
        }
      },
      {
        key: "bindCameraHandlers",
        value: function() {
          var r = this;
          return this.activeListeners.camera = function() {
            r.scheduleRender();
          }, this.camera.on("updated", this.activeListeners.camera), this;
        }
      },
      {
        key: "unbindCameraHandlers",
        value: function() {
          return this.camera.removeListener("updated", this.activeListeners.camera), this;
        }
      },
      {
        key: "getNodeAtPosition",
        value: function(r) {
          var i = r.x, o = r.y, s = Wd(this.webGLContexts.nodes, this.frameBuffers.nodes, i, o, this.pixelRatio, this.pickingDownSizingRatio), a = Hd.apply(void 0, uf(s)), l = this.itemIDsIndex[a];
          return l && l.type === "node" ? l.id : null;
        }
      },
      {
        key: "bindEventHandlers",
        value: function() {
          var r = this;
          this.activeListeners.handleResize = function() {
            r.scheduleRefresh();
          }, window.addEventListener("resize", this.activeListeners.handleResize), this.activeListeners.handleMove = function(o) {
            var s = Ui(o), a = {
              event: s,
              preventSigmaDefault: function() {
                s.preventSigmaDefault();
              }
            }, l = r.getNodeAtPosition(s);
            if (l && r.hoveredNode !== l && !r.nodeDataCache[l].hidden) {
              r.hoveredNode && r.emit("leaveNode", te(te({}, a), {}, {
                node: r.hoveredNode
              })), r.hoveredNode = l, r.emit("enterNode", te(te({}, a), {}, {
                node: l
              })), r.scheduleHighlightedNodesRender();
              return;
            }
            if (r.hoveredNode && r.getNodeAtPosition(s) !== r.hoveredNode) {
              var c = r.hoveredNode;
              r.hoveredNode = null, r.emit("leaveNode", te(te({}, a), {}, {
                node: c
              })), r.scheduleHighlightedNodesRender();
              return;
            }
            if (r.settings.enableEdgeEvents) {
              var h = r.hoveredNode ? null : r.getEdgeAtPoint(a.event.x, a.event.y);
              h !== r.hoveredEdge && (r.hoveredEdge && r.emit("leaveEdge", te(te({}, a), {}, {
                edge: r.hoveredEdge
              })), h && r.emit("enterEdge", te(te({}, a), {}, {
                edge: h
              })), r.hoveredEdge = h);
            }
          }, this.activeListeners.handleMoveBody = function(o) {
            var s = Ui(o);
            r.emit("moveBody", {
              event: s,
              preventSigmaDefault: function() {
                s.preventSigmaDefault();
              }
            });
          }, this.activeListeners.handleLeave = function(o) {
            var s = Ui(o), a = {
              event: s,
              preventSigmaDefault: function() {
                s.preventSigmaDefault();
              }
            };
            r.hoveredNode && (r.emit("leaveNode", te(te({}, a), {}, {
              node: r.hoveredNode
            })), r.scheduleHighlightedNodesRender()), r.settings.enableEdgeEvents && r.hoveredEdge && (r.emit("leaveEdge", te(te({}, a), {}, {
              edge: r.hoveredEdge
            })), r.scheduleHighlightedNodesRender()), r.emit("leaveStage", te({}, a));
          }, this.activeListeners.handleEnter = function(o) {
            var s = Ui(o), a = {
              event: s,
              preventSigmaDefault: function() {
                s.preventSigmaDefault();
              }
            };
            r.emit("enterStage", te({}, a));
          };
          var i = function(s) {
            return function(a) {
              var l = Ui(a), c = {
                event: l,
                preventSigmaDefault: function() {
                  l.preventSigmaDefault();
                }
              }, h = r.getNodeAtPosition(l);
              if (h) return r.emit("".concat(s, "Node"), te(te({}, c), {}, {
                node: h
              }));
              if (r.settings.enableEdgeEvents) {
                var f = r.getEdgeAtPoint(l.x, l.y);
                if (f) return r.emit("".concat(s, "Edge"), te(te({}, c), {}, {
                  edge: f
                }));
              }
              return r.emit("".concat(s, "Stage"), c);
            };
          };
          return this.activeListeners.handleClick = i("click"), this.activeListeners.handleRightClick = i("rightClick"), this.activeListeners.handleDoubleClick = i("doubleClick"), this.activeListeners.handleWheel = i("wheel"), this.activeListeners.handleDown = i("down"), this.activeListeners.handleUp = i("up"), this.mouseCaptor.on("mousemove", this.activeListeners.handleMove), this.mouseCaptor.on("mousemovebody", this.activeListeners.handleMoveBody), this.mouseCaptor.on("click", this.activeListeners.handleClick), this.mouseCaptor.on("rightClick", this.activeListeners.handleRightClick), this.mouseCaptor.on("doubleClick", this.activeListeners.handleDoubleClick), this.mouseCaptor.on("wheel", this.activeListeners.handleWheel), this.mouseCaptor.on("mousedown", this.activeListeners.handleDown), this.mouseCaptor.on("mouseup", this.activeListeners.handleUp), this.mouseCaptor.on("mouseleave", this.activeListeners.handleLeave), this.mouseCaptor.on("mouseenter", this.activeListeners.handleEnter), this.touchCaptor.on("touchdown", this.activeListeners.handleDown), this.touchCaptor.on("touchdown", this.activeListeners.handleMove), this.touchCaptor.on("touchup", this.activeListeners.handleUp), this.touchCaptor.on("touchmove", this.activeListeners.handleMove), this.touchCaptor.on("tap", this.activeListeners.handleClick), this.touchCaptor.on("doubletap", this.activeListeners.handleDoubleClick), this.touchCaptor.on("touchmove", this.activeListeners.handleMoveBody), this;
        }
      },
      {
        key: "bindGraphHandlers",
        value: function() {
          var r = this, i = this.graph, o = /* @__PURE__ */ new Set([
            "x",
            "y",
            "zIndex",
            "type"
          ]);
          return this.activeListeners.eachNodeAttributesUpdatedGraphUpdate = function(s) {
            var a, l = (a = s.hints) === null || a === void 0 ? void 0 : a.attributes;
            r.graph.forEachNode(function(h) {
              return r.updateNode(h);
            });
            var c = !l || l.some(function(h) {
              return o.has(h);
            });
            r.refresh({
              partialGraph: {
                nodes: i.nodes()
              },
              skipIndexation: !c,
              schedule: true
            });
          }, this.activeListeners.eachEdgeAttributesUpdatedGraphUpdate = function(s) {
            var a, l = (a = s.hints) === null || a === void 0 ? void 0 : a.attributes;
            r.graph.forEachEdge(function(h) {
              return r.updateEdge(h);
            });
            var c = l && [
              "zIndex",
              "type"
            ].some(function(h) {
              return l == null ? void 0 : l.includes(h);
            });
            r.refresh({
              partialGraph: {
                edges: i.edges()
              },
              skipIndexation: !c,
              schedule: true
            });
          }, this.activeListeners.addNodeGraphUpdate = function(s) {
            var a = s.key;
            r.addNode(a), r.refresh({
              partialGraph: {
                nodes: [
                  a
                ]
              },
              skipIndexation: false,
              schedule: true
            });
          }, this.activeListeners.updateNodeGraphUpdate = function(s) {
            var a = s.key;
            r.refresh({
              partialGraph: {
                nodes: [
                  a
                ]
              },
              skipIndexation: false,
              schedule: true
            });
          }, this.activeListeners.dropNodeGraphUpdate = function(s) {
            var a = s.key;
            r.removeNode(a), r.refresh({
              schedule: true
            });
          }, this.activeListeners.addEdgeGraphUpdate = function(s) {
            var a = s.key;
            r.addEdge(a), r.refresh({
              partialGraph: {
                edges: [
                  a
                ]
              },
              schedule: true
            });
          }, this.activeListeners.updateEdgeGraphUpdate = function(s) {
            var a = s.key;
            r.refresh({
              partialGraph: {
                edges: [
                  a
                ]
              },
              skipIndexation: false,
              schedule: true
            });
          }, this.activeListeners.dropEdgeGraphUpdate = function(s) {
            var a = s.key;
            r.removeEdge(a), r.refresh({
              schedule: true
            });
          }, this.activeListeners.clearEdgesGraphUpdate = function() {
            r.clearEdgeState(), r.clearEdgeIndices(), r.refresh({
              schedule: true
            });
          }, this.activeListeners.clearGraphUpdate = function() {
            r.clearEdgeState(), r.clearNodeState(), r.clearEdgeIndices(), r.clearNodeIndices(), r.refresh({
              schedule: true
            });
          }, i.on("nodeAdded", this.activeListeners.addNodeGraphUpdate), i.on("nodeDropped", this.activeListeners.dropNodeGraphUpdate), i.on("nodeAttributesUpdated", this.activeListeners.updateNodeGraphUpdate), i.on("eachNodeAttributesUpdated", this.activeListeners.eachNodeAttributesUpdatedGraphUpdate), i.on("edgeAdded", this.activeListeners.addEdgeGraphUpdate), i.on("edgeDropped", this.activeListeners.dropEdgeGraphUpdate), i.on("edgeAttributesUpdated", this.activeListeners.updateEdgeGraphUpdate), i.on("eachEdgeAttributesUpdated", this.activeListeners.eachEdgeAttributesUpdatedGraphUpdate), i.on("edgesCleared", this.activeListeners.clearEdgesGraphUpdate), i.on("cleared", this.activeListeners.clearGraphUpdate), this;
        }
      },
      {
        key: "unbindGraphHandlers",
        value: function() {
          var r = this.graph;
          r.removeListener("nodeAdded", this.activeListeners.addNodeGraphUpdate), r.removeListener("nodeDropped", this.activeListeners.dropNodeGraphUpdate), r.removeListener("nodeAttributesUpdated", this.activeListeners.updateNodeGraphUpdate), r.removeListener("eachNodeAttributesUpdated", this.activeListeners.eachNodeAttributesUpdatedGraphUpdate), r.removeListener("edgeAdded", this.activeListeners.addEdgeGraphUpdate), r.removeListener("edgeDropped", this.activeListeners.dropEdgeGraphUpdate), r.removeListener("edgeAttributesUpdated", this.activeListeners.updateEdgeGraphUpdate), r.removeListener("eachEdgeAttributesUpdated", this.activeListeners.eachEdgeAttributesUpdatedGraphUpdate), r.removeListener("edgesCleared", this.activeListeners.clearEdgesGraphUpdate), r.removeListener("cleared", this.activeListeners.clearGraphUpdate);
        }
      },
      {
        key: "getEdgeAtPoint",
        value: function(r, i) {
          var o = Wd(this.webGLContexts.edges, this.frameBuffers.edges, r, i, this.pixelRatio, this.pickingDownSizingRatio), s = Hd.apply(void 0, uf(o)), a = this.itemIDsIndex[s];
          return a && a.type === "edge" ? a.id : null;
        }
      },
      {
        key: "process",
        value: function() {
          var r = this;
          this.emit("beforeProcess");
          var i = this.graph, o = this.settings, s = this.getDimensions();
          if (this.nodeExtent = tE(this.graph), !this.settings.autoRescale) {
            var a = s.width, l = s.height, c = this.nodeExtent, h = c.x, f = c.y;
            this.nodeExtent = {
              x: [
                (h[0] + h[1]) / 2 - a / 2,
                (h[0] + h[1]) / 2 + a / 2
              ],
              y: [
                (f[0] + f[1]) / 2 - l / 2,
                (f[0] + f[1]) / 2 + l / 2
              ]
            };
          }
          this.normalizationFunction = sf(this.customBBox || this.nodeExtent);
          var p = new lf(), y = Gi(p.getState(), s, this.getGraphDimensions(), this.getStagePadding());
          this.labelGrid.resizeAndClear(s, o.labelGridCellSize);
          for (var k = {}, b = {}, I = {}, _ = {}, m = 1, v = i.nodes(), E = 0, A = v.length; E < A; E++) {
            var F = v[E], R = this.nodeDataCache[F], L = i.getNodeAttributes(F);
            R.x = L.x, R.y = L.y, this.normalizationFunction.applyTo(R), typeof R.label == "string" && !R.hidden && this.labelGrid.add(F, R.size, this.framedGraphToViewport(R, {
              matrix: y
            })), k[R.type] = (k[R.type] || 0) + 1;
          }
          this.labelGrid.organize();
          for (var C in this.nodePrograms) {
            if (!Un.call(this.nodePrograms, C)) throw new Error('Sigma: could not find a suitable program for node type "'.concat(C, '"!'));
            this.nodePrograms[C].reallocate(k[C] || 0), k[C] = 0;
          }
          this.settings.zIndex && this.nodeZExtent[0] !== this.nodeZExtent[1] && (v = of(this.nodeZExtent, function(_e) {
            return r.nodeDataCache[_e].zIndex;
          }, v));
          for (var N = 0, V = v.length; N < V; N++) {
            var B = v[N];
            b[B] = m, _[b[B]] = {
              type: "node",
              id: B
            }, m++;
            var K = this.nodeDataCache[B];
            this.addNodeToProgram(B, b[B], k[K.type]++);
          }
          for (var O = {}, re = i.edges(), ae = 0, J = re.length; ae < J; ae++) {
            var S = re[ae], j = this.edgeDataCache[S];
            O[j.type] = (O[j.type] || 0) + 1;
          }
          this.settings.zIndex && this.edgeZExtent[0] !== this.edgeZExtent[1] && (re = of(this.edgeZExtent, function(_e) {
            return r.edgeDataCache[_e].zIndex;
          }, re));
          for (var H in this.edgePrograms) {
            if (!Un.call(this.edgePrograms, H)) throw new Error('Sigma: could not find a suitable program for edge type "'.concat(H, '"!'));
            this.edgePrograms[H].reallocate(O[H] || 0), O[H] = 0;
          }
          for (var D = 0, x = re.length; D < x; D++) {
            var Q = re[D];
            I[Q] = m, _[I[Q]] = {
              type: "edge",
              id: Q
            }, m++;
            var ie = this.edgeDataCache[Q];
            this.addEdgeToProgram(Q, I[Q], O[ie.type]++);
          }
          return this.itemIDsIndex = _, this.nodeIndices = b, this.edgeIndices = I, this.emit("afterProcess"), this;
        }
      },
      {
        key: "handleSettingsUpdate",
        value: function(r) {
          var i = this, o = this.settings;
          if (this.camera.minRatio = o.minCameraRatio, this.camera.maxRatio = o.maxCameraRatio, this.camera.enabledZooming = o.enableCameraZooming, this.camera.enabledPanning = o.enableCameraPanning, this.camera.enabledRotation = o.enableCameraRotation, o.cameraPanBoundaries ? this.camera.clean = function(h) {
            return i.cleanCameraState(h, o.cameraPanBoundaries && hu(o.cameraPanBoundaries) === "object" ? o.cameraPanBoundaries : {});
          } : this.camera.clean = null, this.camera.setState(this.camera.validateState(this.camera.getState())), r) {
            if (r.edgeProgramClasses !== o.edgeProgramClasses) {
              for (var s in o.edgeProgramClasses) o.edgeProgramClasses[s] !== r.edgeProgramClasses[s] && this.registerEdgeProgram(s, o.edgeProgramClasses[s]);
              for (var a in r.edgeProgramClasses) o.edgeProgramClasses[a] || this.unregisterEdgeProgram(a);
            }
            if (r.nodeProgramClasses !== o.nodeProgramClasses || r.nodeHoverProgramClasses !== o.nodeHoverProgramClasses) {
              for (var l in o.nodeProgramClasses) (o.nodeProgramClasses[l] !== r.nodeProgramClasses[l] || o.nodeHoverProgramClasses[l] !== r.nodeHoverProgramClasses[l]) && this.registerNodeProgram(l, o.nodeProgramClasses[l], o.nodeHoverProgramClasses[l]);
              for (var c in r.nodeProgramClasses) o.nodeProgramClasses[c] || this.unregisterNodeProgram(c);
            }
          }
          return this.mouseCaptor.setSettings(this.settings), this.touchCaptor.setSettings(this.settings), this;
        }
      },
      {
        key: "cleanCameraState",
        value: function(r) {
          var i = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : {}, o = i.tolerance, s = o === void 0 ? 0 : o, a = i.boundaries, l = te({}, r), c = a || this.nodeExtent, h = vi(c.x, 2), f = h[0], p = h[1], y = vi(c.y, 2), k = y[0], b = y[1], I = [
            this.graphToViewport({
              x: f,
              y: k
            }, {
              cameraState: r
            }),
            this.graphToViewport({
              x: p,
              y: k
            }, {
              cameraState: r
            }),
            this.graphToViewport({
              x: f,
              y: b
            }, {
              cameraState: r
            }),
            this.graphToViewport({
              x: p,
              y: b
            }, {
              cameraState: r
            })
          ], _ = 1 / 0, m = -1 / 0, v = 1 / 0, E = -1 / 0;
          I.forEach(function(O) {
            var re = O.x, ae = O.y;
            _ = Math.min(_, re), m = Math.max(m, re), v = Math.min(v, ae), E = Math.max(E, ae);
          });
          var A = m - _, F = E - v, R = this.getDimensions(), L = R.width, C = R.height, N = 0, V = 0;
          if (A >= L ? m < L - s ? N = m - (L - s) : _ > s && (N = _ - s) : m > L + s ? N = m - (L + s) : _ < -s && (N = _ + s), F >= C ? E < C - s ? V = E - (C - s) : v > s && (V = v - s) : E > C + s ? V = E - (C + s) : v < -s && (V = v + s), N || V) {
            var B = this.viewportToFramedGraph({
              x: 0,
              y: 0
            }, {
              cameraState: r
            }), K = this.viewportToFramedGraph({
              x: N,
              y: V
            }, {
              cameraState: r
            });
            N = K.x - B.x, V = K.y - B.y, l.x += N, l.y += V;
          }
          return l;
        }
      },
      {
        key: "renderLabels",
        value: function() {
          if (!this.settings.renderLabels) return this;
          var r = this.camera.getState(), i = this.labelGrid.getLabelsToDisplay(r.ratio, this.settings.labelDensity);
          af(i, this.nodesWithForcedLabels), this.displayedNodeLabels = /* @__PURE__ */ new Set();
          for (var o = this.canvasContexts.labels, s = 0, a = i.length; s < a; s++) {
            var l = i[s], c = this.nodeDataCache[l];
            if (!this.displayedNodeLabels.has(l) && !c.hidden) {
              var h = this.framedGraphToViewport(c), f = h.x, p = h.y, y = this.scaleSize(c.size);
              if (!(!c.forceLabel && y < this.settings.labelRenderedSizeThreshold) && !(f < -ff || f > this.width + ff || p < -hf || p > this.height + hf)) {
                this.displayedNodeLabels.add(l);
                var k = this.settings.defaultDrawNodeLabel, b = this.nodePrograms[c.type], I = (b == null ? void 0 : b.drawLabel) || k;
                I(o, te(te({
                  key: l
                }, c), {}, {
                  size: y,
                  x: f,
                  y: p
                }), this.settings);
              }
            }
          }
          return this;
        }
      },
      {
        key: "renderEdgeLabels",
        value: function() {
          if (!this.settings.renderEdgeLabels) return this;
          var r = this.canvasContexts.edgeLabels;
          r.clearRect(0, 0, this.width, this.height);
          var i = wE({
            graph: this.graph,
            hoveredNode: this.hoveredNode,
            displayedNodeLabels: this.displayedNodeLabels,
            highlightedNodes: this.highlightedNodes
          });
          af(i, this.edgesWithForcedLabels);
          for (var o = /* @__PURE__ */ new Set(), s = 0, a = i.length; s < a; s++) {
            var l = i[s], c = this.graph.extremities(l), h = this.nodeDataCache[c[0]], f = this.nodeDataCache[c[1]], p = this.edgeDataCache[l];
            if (!o.has(l) && !(p.hidden || h.hidden || f.hidden)) {
              var y = this.settings.defaultDrawEdgeLabel, k = this.edgePrograms[p.type], b = (k == null ? void 0 : k.drawLabel) || y;
              b(r, te(te({
                key: l
              }, p), {}, {
                size: this.scaleSize(p.size)
              }), te(te(te({
                key: c[0]
              }, h), this.framedGraphToViewport(h)), {}, {
                size: this.scaleSize(h.size)
              }), te(te(te({
                key: c[1]
              }, f), this.framedGraphToViewport(f)), {}, {
                size: this.scaleSize(f.size)
              }), this.settings), o.add(l);
            }
          }
          return this.displayedEdgeLabels = o, this;
        }
      },
      {
        key: "renderHighlightedNodes",
        value: function() {
          var r = this, i = this.canvasContexts.hovers;
          i.clearRect(0, 0, this.width, this.height);
          var o = function(y) {
            var k = r.nodeDataCache[y], b = r.framedGraphToViewport(k), I = b.x, _ = b.y, m = r.scaleSize(k.size), v = r.settings.defaultDrawNodeHover, E = r.nodePrograms[k.type], A = (E == null ? void 0 : E.drawHover) || v;
            A(i, te(te({
              key: y
            }, k), {}, {
              size: m,
              x: I,
              y: _
            }), r.settings);
          }, s = [];
          this.hoveredNode && !this.nodeDataCache[this.hoveredNode].hidden && s.push(this.hoveredNode), this.highlightedNodes.forEach(function(p) {
            p !== r.hoveredNode && s.push(p);
          }), s.forEach(function(p) {
            return o(p);
          });
          var a = {};
          s.forEach(function(p) {
            var y = r.nodeDataCache[p].type;
            a[y] = (a[y] || 0) + 1;
          });
          for (var l in this.nodeHoverPrograms) this.nodeHoverPrograms[l].reallocate(a[l] || 0), a[l] = 0;
          s.forEach(function(p) {
            var y = r.nodeDataCache[p];
            r.nodeHoverPrograms[y.type].process(0, a[y.type]++, y);
          }), this.webGLContexts.hoverNodes.clear(this.webGLContexts.hoverNodes.COLOR_BUFFER_BIT);
          var c = this.getRenderParams();
          for (var h in this.nodeHoverPrograms) {
            var f = this.nodeHoverPrograms[h];
            f.render(c);
          }
        }
      },
      {
        key: "scheduleHighlightedNodesRender",
        value: function() {
          var r = this;
          this.renderHighlightedNodesFrame || this.renderFrame || (this.renderHighlightedNodesFrame = requestAnimationFrame(function() {
            r.renderHighlightedNodesFrame = null, r.renderHighlightedNodes(), r.renderEdgeLabels();
          }));
        }
      },
      {
        key: "render",
        value: function() {
          var r = this;
          this.emit("beforeRender");
          var i = function() {
            return r.emit("afterRender"), r;
          };
          if (this.renderFrame && (cancelAnimationFrame(this.renderFrame), this.renderFrame = null), this.resize(), this.needToProcess && this.process(), this.needToProcess = false, this.clear(), this.pickingLayers.forEach(function(I) {
            return r.resetWebGLTexture(I);
          }), !this.graph.order) return i();
          var o = this.mouseCaptor, s = this.camera.isAnimated() || o.isMoving || o.draggedEvents || o.currentWheelDirection, a = this.camera.getState(), l = this.getDimensions(), c = this.getGraphDimensions(), h = this.getStagePadding();
          this.matrix = Gi(a, l, c, h), this.invMatrix = Gi(a, l, c, h, true), this.correctionRatio = eE(this.matrix, a, l), this.graphToViewportRatio = this.getGraphToViewportRatio();
          var f = this.getRenderParams();
          for (var p in this.nodePrograms) {
            var y = this.nodePrograms[p];
            y.render(f);
          }
          if (!this.settings.hideEdgesOnMove || !s) for (var k in this.edgePrograms) {
            var b = this.edgePrograms[k];
            b.render(f);
          }
          return this.settings.hideLabelsOnMove && s || (this.renderLabels(), this.renderEdgeLabels(), this.renderHighlightedNodes()), i();
        }
      },
      {
        key: "addNode",
        value: function(r) {
          var i = Object.assign({}, this.graph.getNodeAttributes(r));
          this.settings.nodeReducer && (i = this.settings.nodeReducer(r, i));
          var o = EE(this.settings, r, i);
          this.nodeDataCache[r] = o, this.nodesWithForcedLabels.delete(r), o.forceLabel && !o.hidden && this.nodesWithForcedLabels.add(r), this.highlightedNodes.delete(r), o.highlighted && !o.hidden && this.highlightedNodes.add(r), this.settings.zIndex && (o.zIndex < this.nodeZExtent[0] && (this.nodeZExtent[0] = o.zIndex), o.zIndex > this.nodeZExtent[1] && (this.nodeZExtent[1] = o.zIndex));
        }
      },
      {
        key: "updateNode",
        value: function(r) {
          this.addNode(r);
          var i = this.nodeDataCache[r];
          this.normalizationFunction.applyTo(i);
        }
      },
      {
        key: "removeNode",
        value: function(r) {
          delete this.nodeDataCache[r], delete this.nodeProgramIndex[r], this.highlightedNodes.delete(r), this.hoveredNode === r && (this.hoveredNode = null), this.nodesWithForcedLabels.delete(r);
        }
      },
      {
        key: "addEdge",
        value: function(r) {
          var i = Object.assign({}, this.graph.getEdgeAttributes(r));
          this.settings.edgeReducer && (i = this.settings.edgeReducer(r, i));
          var o = SE(this.settings, r, i);
          this.edgeDataCache[r] = o, this.edgesWithForcedLabels.delete(r), o.forceLabel && !o.hidden && this.edgesWithForcedLabels.add(r), this.settings.zIndex && (o.zIndex < this.edgeZExtent[0] && (this.edgeZExtent[0] = o.zIndex), o.zIndex > this.edgeZExtent[1] && (this.edgeZExtent[1] = o.zIndex));
        }
      },
      {
        key: "updateEdge",
        value: function(r) {
          this.addEdge(r);
        }
      },
      {
        key: "removeEdge",
        value: function(r) {
          delete this.edgeDataCache[r], delete this.edgeProgramIndex[r], this.hoveredEdge === r && (this.hoveredEdge = null), this.edgesWithForcedLabels.delete(r);
        }
      },
      {
        key: "clearNodeIndices",
        value: function() {
          this.labelGrid = new df(), this.nodeExtent = {
            x: [
              0,
              1
            ],
            y: [
              0,
              1
            ]
          }, this.nodeDataCache = {}, this.edgeProgramIndex = {}, this.nodesWithForcedLabels = /* @__PURE__ */ new Set(), this.nodeZExtent = [
            1 / 0,
            -1 / 0
          ], this.highlightedNodes = /* @__PURE__ */ new Set();
        }
      },
      {
        key: "clearEdgeIndices",
        value: function() {
          this.edgeDataCache = {}, this.edgeProgramIndex = {}, this.edgesWithForcedLabels = /* @__PURE__ */ new Set(), this.edgeZExtent = [
            1 / 0,
            -1 / 0
          ];
        }
      },
      {
        key: "clearIndices",
        value: function() {
          this.clearEdgeIndices(), this.clearNodeIndices();
        }
      },
      {
        key: "clearNodeState",
        value: function() {
          this.displayedNodeLabels = /* @__PURE__ */ new Set(), this.highlightedNodes = /* @__PURE__ */ new Set(), this.hoveredNode = null;
        }
      },
      {
        key: "clearEdgeState",
        value: function() {
          this.displayedEdgeLabels = /* @__PURE__ */ new Set(), this.highlightedNodes = /* @__PURE__ */ new Set(), this.hoveredEdge = null;
        }
      },
      {
        key: "clearState",
        value: function() {
          this.clearEdgeState(), this.clearNodeState();
        }
      },
      {
        key: "addNodeToProgram",
        value: function(r, i, o) {
          var s = this.nodeDataCache[r], a = this.nodePrograms[s.type];
          if (!a) throw new Error('Sigma: could not find a suitable program for node type "'.concat(s.type, '"!'));
          a.process(i, o, s), this.nodeProgramIndex[r] = o;
        }
      },
      {
        key: "addEdgeToProgram",
        value: function(r, i, o) {
          var s = this.edgeDataCache[r], a = this.edgePrograms[s.type];
          if (!a) throw new Error('Sigma: could not find a suitable program for edge type "'.concat(s.type, '"!'));
          var l = this.graph.extremities(r), c = this.nodeDataCache[l[0]], h = this.nodeDataCache[l[1]];
          a.process(i, o, c, h, s), this.edgeProgramIndex[r] = o;
        }
      },
      {
        key: "getRenderParams",
        value: function() {
          return {
            matrix: this.matrix,
            invMatrix: this.invMatrix,
            width: this.width,
            height: this.height,
            pixelRatio: this.pixelRatio,
            zoomRatio: this.camera.ratio,
            cameraAngle: this.camera.angle,
            sizeRatio: 1 / this.scaleSize(),
            correctionRatio: this.correctionRatio,
            downSizingRatio: this.pickingDownSizingRatio,
            minEdgeThickness: this.settings.minEdgeThickness,
            antiAliasingFeather: this.settings.antiAliasingFeather
          };
        }
      },
      {
        key: "getStagePadding",
        value: function() {
          var r = this.settings, i = r.stagePadding, o = r.autoRescale;
          return o && i || 0;
        }
      },
      {
        key: "createLayer",
        value: function(r, i) {
          var o = arguments.length > 2 && arguments[2] !== void 0 ? arguments[2] : {};
          if (this.elements[r]) throw new Error('Sigma: a layer named "'.concat(r, '" already exists'));
          var s = rE(i, {
            position: "absolute"
          }, {
            class: "sigma-".concat(r)
          });
          return o.style && Object.assign(s.style, o.style), this.elements[r] = s, "beforeLayer" in o && o.beforeLayer ? this.elements[o.beforeLayer].before(s) : "afterLayer" in o && o.afterLayer ? this.elements[o.afterLayer].after(s) : this.container.appendChild(s), s;
        }
      },
      {
        key: "createCanvas",
        value: function(r) {
          var i = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : {};
          return this.createLayer(r, "canvas", i);
        }
      },
      {
        key: "createCanvasContext",
        value: function(r) {
          var i = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : {}, o = this.createCanvas(r, i), s = {
            preserveDrawingBuffer: false,
            antialias: false
          };
          return this.canvasContexts[r] = o.getContext("2d", s), this;
        }
      },
      {
        key: "createWebGLContext",
        value: function(r) {
          var i = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : {}, o = (i == null ? void 0 : i.canvas) || this.createCanvas(r, i);
          i.hidden && o.remove();
          var s = te({
            preserveDrawingBuffer: false,
            antialias: false
          }, i), a;
          a = o.getContext("webgl2", s), a || (a = o.getContext("webgl", s)), a || (a = o.getContext("experimental-webgl", s));
          var l = a;
          if (this.webGLContexts[r] = l, l.blendFunc(l.ONE, l.ONE_MINUS_SRC_ALPHA), i.picking) {
            this.pickingLayers.add(r);
            var c = l.createFramebuffer();
            if (!c) throw new Error("Sigma: cannot create a new frame buffer for layer ".concat(r));
            this.frameBuffers[r] = c;
          }
          return l;
        }
      },
      {
        key: "killLayer",
        value: function(r) {
          var i = this.elements[r];
          if (!i) throw new Error("Sigma: cannot kill layer ".concat(r, ", which does not exist"));
          if (this.webGLContexts[r]) {
            var o, s = this.webGLContexts[r];
            (o = s.getExtension("WEBGL_lose_context")) === null || o === void 0 || o.loseContext(), delete this.webGLContexts[r];
          } else this.canvasContexts[r] && delete this.canvasContexts[r];
          return i.remove(), delete this.elements[r], this;
        }
      },
      {
        key: "getCamera",
        value: function() {
          return this.camera;
        }
      },
      {
        key: "setCamera",
        value: function(r) {
          this.unbindCameraHandlers(), this.camera = r, this.bindCameraHandlers();
        }
      },
      {
        key: "getContainer",
        value: function() {
          return this.container;
        }
      },
      {
        key: "getGraph",
        value: function() {
          return this.graph;
        }
      },
      {
        key: "setGraph",
        value: function(r) {
          r !== this.graph && (this.hoveredNode && !r.hasNode(this.hoveredNode) && (this.hoveredNode = null), this.hoveredEdge && !r.hasEdge(this.hoveredEdge) && (this.hoveredEdge = null), this.unbindGraphHandlers(), this.checkEdgesEventsFrame !== null && (cancelAnimationFrame(this.checkEdgesEventsFrame), this.checkEdgesEventsFrame = null), this.graph = r, this.bindGraphHandlers(), this.refresh());
        }
      },
      {
        key: "getMouseCaptor",
        value: function() {
          return this.mouseCaptor;
        }
      },
      {
        key: "getTouchCaptor",
        value: function() {
          return this.touchCaptor;
        }
      },
      {
        key: "getDimensions",
        value: function() {
          return {
            width: this.width,
            height: this.height
          };
        }
      },
      {
        key: "getGraphDimensions",
        value: function() {
          var r = this.customBBox || this.nodeExtent;
          return {
            width: r.x[1] - r.x[0] || 1,
            height: r.y[1] - r.y[0] || 1
          };
        }
      },
      {
        key: "getNodeDisplayData",
        value: function(r) {
          var i = this.nodeDataCache[r];
          return i ? Object.assign({}, i) : void 0;
        }
      },
      {
        key: "getEdgeDisplayData",
        value: function(r) {
          var i = this.edgeDataCache[r];
          return i ? Object.assign({}, i) : void 0;
        }
      },
      {
        key: "getNodeDisplayedLabels",
        value: function() {
          return new Set(this.displayedNodeLabels);
        }
      },
      {
        key: "getEdgeDisplayedLabels",
        value: function() {
          return new Set(this.displayedEdgeLabels);
        }
      },
      {
        key: "getSettings",
        value: function() {
          return te({}, this.settings);
        }
      },
      {
        key: "getSetting",
        value: function(r) {
          return this.settings[r];
        }
      },
      {
        key: "setSetting",
        value: function(r, i) {
          var o = te({}, this.settings);
          return this.settings[r] = i, al(this.settings), this.handleSettingsUpdate(o), this.scheduleRefresh(), this;
        }
      },
      {
        key: "updateSetting",
        value: function(r, i) {
          return this.setSetting(r, i(this.settings[r])), this;
        }
      },
      {
        key: "setSettings",
        value: function(r) {
          var i = te({}, this.settings);
          return this.settings = te(te({}, this.settings), r), al(this.settings), this.handleSettingsUpdate(i), this.scheduleRefresh(), this;
        }
      },
      {
        key: "resize",
        value: function(r) {
          var i = this.width, o = this.height;
          if (this.width = this.container.offsetWidth, this.height = this.container.offsetHeight, this.pixelRatio = rf(), this.width === 0) if (this.settings.allowInvalidContainer) this.width = 1;
          else throw new Error("Sigma: Container has no width. You can set the allowInvalidContainer setting to true to stop seeing this error.");
          if (this.height === 0) if (this.settings.allowInvalidContainer) this.height = 1;
          else throw new Error("Sigma: Container has no height. You can set the allowInvalidContainer setting to true to stop seeing this error.");
          if (!r && i === this.width && o === this.height) return this;
          for (var s in this.elements) {
            var a = this.elements[s];
            a.style.width = this.width + "px", a.style.height = this.height + "px";
          }
          for (var l in this.canvasContexts) this.elements[l].setAttribute("width", this.width * this.pixelRatio + "px"), this.elements[l].setAttribute("height", this.height * this.pixelRatio + "px"), this.pixelRatio !== 1 && this.canvasContexts[l].scale(this.pixelRatio, this.pixelRatio);
          for (var c in this.webGLContexts) {
            this.elements[c].setAttribute("width", this.width * this.pixelRatio + "px"), this.elements[c].setAttribute("height", this.height * this.pixelRatio + "px");
            var h = this.webGLContexts[c];
            if (h.viewport(0, 0, this.width * this.pixelRatio, this.height * this.pixelRatio), this.pickingLayers.has(c)) {
              var f = this.textures[c];
              f && h.deleteTexture(f);
            }
          }
          return this.emit("resize"), this;
        }
      },
      {
        key: "clear",
        value: function() {
          return this.emit("beforeClear"), this.webGLContexts.nodes.bindFramebuffer(WebGLRenderingContext.FRAMEBUFFER, null), this.webGLContexts.nodes.clear(WebGLRenderingContext.COLOR_BUFFER_BIT), this.webGLContexts.edges.bindFramebuffer(WebGLRenderingContext.FRAMEBUFFER, null), this.webGLContexts.edges.clear(WebGLRenderingContext.COLOR_BUFFER_BIT), this.webGLContexts.hoverNodes.clear(WebGLRenderingContext.COLOR_BUFFER_BIT), this.canvasContexts.labels.clearRect(0, 0, this.width, this.height), this.canvasContexts.hovers.clearRect(0, 0, this.width, this.height), this.canvasContexts.edgeLabels.clearRect(0, 0, this.width, this.height), this.emit("afterClear"), this;
        }
      },
      {
        key: "refresh",
        value: function(r) {
          var i = this, o = (r == null ? void 0 : r.skipIndexation) !== void 0 ? r == null ? void 0 : r.skipIndexation : false, s = (r == null ? void 0 : r.schedule) !== void 0 ? r.schedule : false, a = !r || !r.partialGraph;
          if (a) this.clearEdgeIndices(), this.clearNodeIndices(), this.graph.forEachNode(function(E) {
            return i.addNode(E);
          }), this.graph.forEachEdge(function(E) {
            return i.addEdge(E);
          });
          else {
            for (var l, c, h = ((l = r.partialGraph) === null || l === void 0 ? void 0 : l.nodes) || [], f = 0, p = (h == null ? void 0 : h.length) || 0; f < p; f++) {
              var y = h[f];
              if (this.updateNode(y), o) {
                var k = this.nodeProgramIndex[y];
                if (k === void 0) throw new Error('Sigma: node "'.concat(y, `" can't be repaint`));
                this.addNodeToProgram(y, this.nodeIndices[y], k);
              }
            }
            for (var b = (r == null || (c = r.partialGraph) === null || c === void 0 ? void 0 : c.edges) || [], I = 0, _ = b.length; I < _; I++) {
              var m = b[I];
              if (this.updateEdge(m), o) {
                var v = this.edgeProgramIndex[m];
                if (v === void 0) throw new Error('Sigma: edge "'.concat(m, `" can't be repaint`));
                this.addEdgeToProgram(m, this.edgeIndices[m], v);
              }
            }
          }
          return (a || !o) && (this.needToProcess = true), s ? this.scheduleRender() : this.render(), this;
        }
      },
      {
        key: "scheduleRender",
        value: function() {
          var r = this;
          return this.renderFrame || (this.renderFrame = requestAnimationFrame(function() {
            r.render();
          })), this;
        }
      },
      {
        key: "scheduleRefresh",
        value: function(r) {
          return this.refresh(te(te({}, r), {}, {
            schedule: true
          }));
        }
      },
      {
        key: "getViewportZoomedState",
        value: function(r, i) {
          var o = this.camera.getState(), s = o.ratio, a = o.angle, l = o.x, c = o.y, h = this.settings, f = h.minCameraRatio, p = h.maxCameraRatio;
          typeof p == "number" && (i = Math.min(i, p)), typeof f == "number" && (i = Math.max(i, f));
          var y = i / s, k = {
            x: this.width / 2,
            y: this.height / 2
          }, b = this.viewportToFramedGraph(r), I = this.viewportToFramedGraph(k);
          return {
            angle: a,
            x: (b.x - I.x) * (1 - y) + l,
            y: (b.y - I.y) * (1 - y) + c,
            ratio: i
          };
        }
      },
      {
        key: "viewRectangle",
        value: function() {
          var r = this.viewportToFramedGraph({
            x: 0,
            y: 0
          }), i = this.viewportToFramedGraph({
            x: this.width,
            y: 0
          }), o = this.viewportToFramedGraph({
            x: 0,
            y: this.height
          });
          return {
            x1: r.x,
            y1: r.y,
            x2: i.x,
            y2: i.y,
            height: i.y - o.y
          };
        }
      },
      {
        key: "framedGraphToViewport",
        value: function(r) {
          var i = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : {}, o = !!i.cameraState || !!i.viewportDimensions || !!i.graphDimensions, s = i.matrix ? i.matrix : o ? Gi(i.cameraState || this.camera.getState(), i.viewportDimensions || this.getDimensions(), i.graphDimensions || this.getGraphDimensions(), i.padding || this.getStagePadding()) : this.matrix, a = fu(s, r);
          return {
            x: (1 + a.x) * this.width / 2,
            y: (1 - a.y) * this.height / 2
          };
        }
      },
      {
        key: "viewportToFramedGraph",
        value: function(r) {
          var i = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : {}, o = !!i.cameraState || !!i.viewportDimensions || !i.graphDimensions, s = i.matrix ? i.matrix : o ? Gi(i.cameraState || this.camera.getState(), i.viewportDimensions || this.getDimensions(), i.graphDimensions || this.getGraphDimensions(), i.padding || this.getStagePadding(), true) : this.invMatrix, a = fu(s, {
            x: r.x / this.width * 2 - 1,
            y: 1 - r.y / this.height * 2
          });
          return isNaN(a.x) && (a.x = 0), isNaN(a.y) && (a.y = 0), a;
        }
      },
      {
        key: "viewportToGraph",
        value: function(r) {
          var i = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : {};
          return this.normalizationFunction.inverse(this.viewportToFramedGraph(r, i));
        }
      },
      {
        key: "graphToViewport",
        value: function(r) {
          var i = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : {};
          return this.framedGraphToViewport(this.normalizationFunction(r), i);
        }
      },
      {
        key: "getGraphToViewportRatio",
        value: function() {
          var r = {
            x: 0,
            y: 0
          }, i = {
            x: 1,
            y: 1
          }, o = Math.sqrt(Math.pow(r.x - i.x, 2) + Math.pow(r.y - i.y, 2)), s = this.graphToViewport(r), a = this.graphToViewport(i), l = Math.sqrt(Math.pow(s.x - a.x, 2) + Math.pow(s.y - a.y, 2));
          return l / o;
        }
      },
      {
        key: "getBBox",
        value: function() {
          return this.nodeExtent;
        }
      },
      {
        key: "getCustomBBox",
        value: function() {
          return this.customBBox;
        }
      },
      {
        key: "setCustomBBox",
        value: function(r) {
          return this.customBBox = r, this.scheduleRender(), this;
        }
      },
      {
        key: "kill",
        value: function() {
          this.emit("kill"), this.removeAllListeners(), this.unbindCameraHandlers(), window.removeEventListener("resize", this.activeListeners.handleResize), this.mouseCaptor.kill(), this.touchCaptor.kill(), this.unbindGraphHandlers(), this.clearIndices(), this.clearState(), this.nodeDataCache = {}, this.edgeDataCache = {}, this.highlightedNodes.clear(), this.renderFrame && (cancelAnimationFrame(this.renderFrame), this.renderFrame = null), this.renderHighlightedNodesFrame && (cancelAnimationFrame(this.renderHighlightedNodesFrame), this.renderHighlightedNodesFrame = null);
          for (var r = this.container; r.firstChild; ) r.removeChild(r.firstChild);
          for (var i in this.nodePrograms) this.nodePrograms[i].kill();
          for (var o in this.nodeHoverPrograms) this.nodeHoverPrograms[o].kill();
          for (var s in this.edgePrograms) this.edgePrograms[s].kill();
          this.nodePrograms = {}, this.nodeHoverPrograms = {}, this.edgePrograms = {};
          for (var a in this.elements) this.killLayer(a);
          this.canvasContexts = {}, this.webGLContexts = {}, this.elements = {};
        }
      },
      {
        key: "scaleSize",
        value: function() {
          var r = arguments.length > 0 && arguments[0] !== void 0 ? arguments[0] : 1, i = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : this.camera.ratio;
          return r / this.settings.zoomToSizeRatioFunction(i) * (this.getSetting("itemSizesReference") === "positions" ? i * this.graphToViewportRatio : 1);
        }
      },
      {
        key: "getCanvases",
        value: function() {
          var r = {};
          for (var i in this.elements) this.elements[i] instanceof HTMLCanvasElement && (r[i] = this.elements[i]);
          return r;
        }
      }
    ]);
  }(pc), kE = _E;
  function bE() {
    const e = arguments[0];
    for (let t = 1, n = arguments.length; t < n; t++) if (arguments[t]) for (const r in arguments[t]) e[r] = arguments[t][r];
    return e;
  }
  let it = bE;
  typeof Object.assign == "function" && (it = Object.assign);
  function nn(e, t, n, r) {
    const i = e._nodes.get(t);
    let o = null;
    return i && (r === "mixed" ? o = i.out && i.out[n] || i.undirected && i.undirected[n] : r === "directed" ? o = i.out && i.out[n] : o = i.undirected && i.undirected[n]), o;
  }
  function ht(e) {
    return typeof e == "object" && e !== null;
  }
  function xg(e) {
    let t;
    for (t in e) return false;
    return true;
  }
  function Qt(e, t, n) {
    Object.defineProperty(e, t, {
      enumerable: false,
      configurable: false,
      writable: true,
      value: n
    });
  }
  function fn(e, t, n) {
    const r = {
      enumerable: true,
      configurable: true
    };
    typeof n == "function" ? r.get = n : (r.value = n, r.writable = false), Object.defineProperty(e, t, r);
  }
  function pf(e) {
    return !(!ht(e) || e.attributes && !Array.isArray(e.attributes));
  }
  function xE() {
    let e = Math.floor(Math.random() * 256) & 255;
    return () => e++;
  }
  function jn() {
    const e = arguments;
    let t = null, n = -1;
    return {
      [Symbol.iterator]() {
        return this;
      },
      next() {
        let r = null;
        do {
          if (t === null) {
            if (n++, n >= e.length) return {
              done: true
            };
            t = e[n][Symbol.iterator]();
          }
          if (r = t.next(), r.done) {
            t = null;
            continue;
          }
          break;
        } while (true);
        return r;
      }
    };
  }
  function ki() {
    return {
      [Symbol.iterator]() {
        return this;
      },
      next() {
        return {
          done: true
        };
      }
    };
  }
  class mc extends Error {
    constructor(t) {
      super(), this.name = "GraphError", this.message = t;
    }
  }
  class X extends mc {
    constructor(t) {
      super(t), this.name = "InvalidArgumentsGraphError", typeof Error.captureStackTrace == "function" && Error.captureStackTrace(this, X.prototype.constructor);
    }
  }
  class Y extends mc {
    constructor(t) {
      super(t), this.name = "NotFoundGraphError", typeof Error.captureStackTrace == "function" && Error.captureStackTrace(this, Y.prototype.constructor);
    }
  }
  class ce extends mc {
    constructor(t) {
      super(t), this.name = "UsageGraphError", typeof Error.captureStackTrace == "function" && Error.captureStackTrace(this, ce.prototype.constructor);
    }
  }
  function Cg(e, t) {
    this.key = e, this.attributes = t, this.clear();
  }
  Cg.prototype.clear = function() {
    this.inDegree = 0, this.outDegree = 0, this.undirectedDegree = 0, this.undirectedLoops = 0, this.directedLoops = 0, this.in = {}, this.out = {}, this.undirected = {};
  };
  function Tg(e, t) {
    this.key = e, this.attributes = t, this.clear();
  }
  Tg.prototype.clear = function() {
    this.inDegree = 0, this.outDegree = 0, this.directedLoops = 0, this.in = {}, this.out = {};
  };
  function Rg(e, t) {
    this.key = e, this.attributes = t, this.clear();
  }
  Rg.prototype.clear = function() {
    this.undirectedDegree = 0, this.undirectedLoops = 0, this.undirected = {};
  };
  function bi(e, t, n, r, i) {
    this.key = t, this.attributes = i, this.undirected = e, this.source = n, this.target = r;
  }
  bi.prototype.attach = function() {
    let e = "out", t = "in";
    this.undirected && (e = t = "undirected");
    const n = this.source.key, r = this.target.key;
    this.source[e][r] = this, !(this.undirected && n === r) && (this.target[t][n] = this);
  };
  bi.prototype.attachMulti = function() {
    let e = "out", t = "in";
    const n = this.source.key, r = this.target.key;
    this.undirected && (e = t = "undirected");
    const i = this.source[e], o = i[r];
    if (typeof o > "u") {
      i[r] = this, this.undirected && n === r || (this.target[t][n] = this);
      return;
    }
    o.previous = this, this.next = o, i[r] = this, this.target[t][n] = this;
  };
  bi.prototype.detach = function() {
    const e = this.source.key, t = this.target.key;
    let n = "out", r = "in";
    this.undirected && (n = r = "undirected"), delete this.source[n][t], delete this.target[r][e];
  };
  bi.prototype.detachMulti = function() {
    const e = this.source.key, t = this.target.key;
    let n = "out", r = "in";
    this.undirected && (n = r = "undirected"), this.previous === void 0 ? this.next === void 0 ? (delete this.source[n][t], delete this.target[r][e]) : (this.next.previous = void 0, this.source[n][t] = this.next, this.target[r][e] = this.next) : (this.previous.next = this.next, this.next !== void 0 && (this.next.previous = this.previous));
  };
  const Ag = 0, Lg = 1, CE = 2, Ig = 3;
  function Qn(e, t, n, r, i, o, s) {
    let a, l, c, h;
    if (r = "" + r, n === Ag) {
      if (a = e._nodes.get(r), !a) throw new Y(`Graph.${t}: could not find the "${r}" node in the graph.`);
      c = i, h = o;
    } else if (n === Ig) {
      if (i = "" + i, l = e._edges.get(i), !l) throw new Y(`Graph.${t}: could not find the "${i}" edge in the graph.`);
      const f = l.source.key, p = l.target.key;
      if (r === f) a = l.target;
      else if (r === p) a = l.source;
      else throw new Y(`Graph.${t}: the "${r}" node is not attached to the "${i}" edge (${f}, ${p}).`);
      c = o, h = s;
    } else {
      if (l = e._edges.get(r), !l) throw new Y(`Graph.${t}: could not find the "${r}" edge in the graph.`);
      n === Lg ? a = l.source : a = l.target, c = i, h = o;
    }
    return [
      a,
      c,
      h
    ];
  }
  function TE(e, t, n) {
    e.prototype[t] = function(r, i, o) {
      const [s, a] = Qn(this, t, n, r, i, o);
      return s.attributes[a];
    };
  }
  function RE(e, t, n) {
    e.prototype[t] = function(r, i) {
      const [o] = Qn(this, t, n, r, i);
      return o.attributes;
    };
  }
  function AE(e, t, n) {
    e.prototype[t] = function(r, i, o) {
      const [s, a] = Qn(this, t, n, r, i, o);
      return s.attributes.hasOwnProperty(a);
    };
  }
  function LE(e, t, n) {
    e.prototype[t] = function(r, i, o, s) {
      const [a, l, c] = Qn(this, t, n, r, i, o, s);
      return a.attributes[l] = c, this.emit("nodeAttributesUpdated", {
        key: a.key,
        type: "set",
        attributes: a.attributes,
        name: l
      }), this;
    };
  }
  function IE(e, t, n) {
    e.prototype[t] = function(r, i, o, s) {
      const [a, l, c] = Qn(this, t, n, r, i, o, s);
      if (typeof c != "function") throw new X(`Graph.${t}: updater should be a function.`);
      const h = a.attributes, f = c(h[l]);
      return h[l] = f, this.emit("nodeAttributesUpdated", {
        key: a.key,
        type: "set",
        attributes: a.attributes,
        name: l
      }), this;
    };
  }
  function DE(e, t, n) {
    e.prototype[t] = function(r, i, o) {
      const [s, a] = Qn(this, t, n, r, i, o);
      return delete s.attributes[a], this.emit("nodeAttributesUpdated", {
        key: s.key,
        type: "remove",
        attributes: s.attributes,
        name: a
      }), this;
    };
  }
  function PE(e, t, n) {
    e.prototype[t] = function(r, i, o) {
      const [s, a] = Qn(this, t, n, r, i, o);
      if (!ht(a)) throw new X(`Graph.${t}: provided attributes are not a plain object.`);
      return s.attributes = a, this.emit("nodeAttributesUpdated", {
        key: s.key,
        type: "replace",
        attributes: s.attributes
      }), this;
    };
  }
  function NE(e, t, n) {
    e.prototype[t] = function(r, i, o) {
      const [s, a] = Qn(this, t, n, r, i, o);
      if (!ht(a)) throw new X(`Graph.${t}: provided attributes are not a plain object.`);
      return it(s.attributes, a), this.emit("nodeAttributesUpdated", {
        key: s.key,
        type: "merge",
        attributes: s.attributes,
        data: a
      }), this;
    };
  }
  function FE(e, t, n) {
    e.prototype[t] = function(r, i, o) {
      const [s, a] = Qn(this, t, n, r, i, o);
      if (typeof a != "function") throw new X(`Graph.${t}: provided updater is not a function.`);
      return s.attributes = a(s.attributes), this.emit("nodeAttributesUpdated", {
        key: s.key,
        type: "update",
        attributes: s.attributes
      }), this;
    };
  }
  const zE = [
    {
      name: (e) => `get${e}Attribute`,
      attacher: TE
    },
    {
      name: (e) => `get${e}Attributes`,
      attacher: RE
    },
    {
      name: (e) => `has${e}Attribute`,
      attacher: AE
    },
    {
      name: (e) => `set${e}Attribute`,
      attacher: LE
    },
    {
      name: (e) => `update${e}Attribute`,
      attacher: IE
    },
    {
      name: (e) => `remove${e}Attribute`,
      attacher: DE
    },
    {
      name: (e) => `replace${e}Attributes`,
      attacher: PE
    },
    {
      name: (e) => `merge${e}Attributes`,
      attacher: NE
    },
    {
      name: (e) => `update${e}Attributes`,
      attacher: FE
    }
  ];
  function OE(e) {
    zE.forEach(function({ name: t, attacher: n }) {
      n(e, t("Node"), Ag), n(e, t("Source"), Lg), n(e, t("Target"), CE), n(e, t("Opposite"), Ig);
    });
  }
  function GE(e, t, n) {
    e.prototype[t] = function(r, i) {
      let o;
      if (this.type !== "mixed" && n !== "mixed" && n !== this.type) throw new ce(`Graph.${t}: cannot find this type of edges in your ${this.type} graph.`);
      if (arguments.length > 2) {
        if (this.multi) throw new ce(`Graph.${t}: cannot use a {source,target} combo when asking about an edge's attributes in a MultiGraph since we cannot infer the one you want information about.`);
        const s = "" + r, a = "" + i;
        if (i = arguments[2], o = nn(this, s, a, n), !o) throw new Y(`Graph.${t}: could not find an edge for the given path ("${s}" - "${a}").`);
      } else {
        if (n !== "mixed") throw new ce(`Graph.${t}: calling this method with only a key (vs. a source and target) does not make sense since an edge with this key could have the other type.`);
        if (r = "" + r, o = this._edges.get(r), !o) throw new Y(`Graph.${t}: could not find the "${r}" edge in the graph.`);
      }
      return o.attributes[i];
    };
  }
  function UE(e, t, n) {
    e.prototype[t] = function(r) {
      let i;
      if (this.type !== "mixed" && n !== "mixed" && n !== this.type) throw new ce(`Graph.${t}: cannot find this type of edges in your ${this.type} graph.`);
      if (arguments.length > 1) {
        if (this.multi) throw new ce(`Graph.${t}: cannot use a {source,target} combo when asking about an edge's attributes in a MultiGraph since we cannot infer the one you want information about.`);
        const o = "" + r, s = "" + arguments[1];
        if (i = nn(this, o, s, n), !i) throw new Y(`Graph.${t}: could not find an edge for the given path ("${o}" - "${s}").`);
      } else {
        if (n !== "mixed") throw new ce(`Graph.${t}: calling this method with only a key (vs. a source and target) does not make sense since an edge with this key could have the other type.`);
        if (r = "" + r, i = this._edges.get(r), !i) throw new Y(`Graph.${t}: could not find the "${r}" edge in the graph.`);
      }
      return i.attributes;
    };
  }
  function BE(e, t, n) {
    e.prototype[t] = function(r, i) {
      let o;
      if (this.type !== "mixed" && n !== "mixed" && n !== this.type) throw new ce(`Graph.${t}: cannot find this type of edges in your ${this.type} graph.`);
      if (arguments.length > 2) {
        if (this.multi) throw new ce(`Graph.${t}: cannot use a {source,target} combo when asking about an edge's attributes in a MultiGraph since we cannot infer the one you want information about.`);
        const s = "" + r, a = "" + i;
        if (i = arguments[2], o = nn(this, s, a, n), !o) throw new Y(`Graph.${t}: could not find an edge for the given path ("${s}" - "${a}").`);
      } else {
        if (n !== "mixed") throw new ce(`Graph.${t}: calling this method with only a key (vs. a source and target) does not make sense since an edge with this key could have the other type.`);
        if (r = "" + r, o = this._edges.get(r), !o) throw new Y(`Graph.${t}: could not find the "${r}" edge in the graph.`);
      }
      return o.attributes.hasOwnProperty(i);
    };
  }
  function ME(e, t, n) {
    e.prototype[t] = function(r, i, o) {
      let s;
      if (this.type !== "mixed" && n !== "mixed" && n !== this.type) throw new ce(`Graph.${t}: cannot find this type of edges in your ${this.type} graph.`);
      if (arguments.length > 3) {
        if (this.multi) throw new ce(`Graph.${t}: cannot use a {source,target} combo when asking about an edge's attributes in a MultiGraph since we cannot infer the one you want information about.`);
        const a = "" + r, l = "" + i;
        if (i = arguments[2], o = arguments[3], s = nn(this, a, l, n), !s) throw new Y(`Graph.${t}: could not find an edge for the given path ("${a}" - "${l}").`);
      } else {
        if (n !== "mixed") throw new ce(`Graph.${t}: calling this method with only a key (vs. a source and target) does not make sense since an edge with this key could have the other type.`);
        if (r = "" + r, s = this._edges.get(r), !s) throw new Y(`Graph.${t}: could not find the "${r}" edge in the graph.`);
      }
      return s.attributes[i] = o, this.emit("edgeAttributesUpdated", {
        key: s.key,
        type: "set",
        attributes: s.attributes,
        name: i
      }), this;
    };
  }
  function $E(e, t, n) {
    e.prototype[t] = function(r, i, o) {
      let s;
      if (this.type !== "mixed" && n !== "mixed" && n !== this.type) throw new ce(`Graph.${t}: cannot find this type of edges in your ${this.type} graph.`);
      if (arguments.length > 3) {
        if (this.multi) throw new ce(`Graph.${t}: cannot use a {source,target} combo when asking about an edge's attributes in a MultiGraph since we cannot infer the one you want information about.`);
        const a = "" + r, l = "" + i;
        if (i = arguments[2], o = arguments[3], s = nn(this, a, l, n), !s) throw new Y(`Graph.${t}: could not find an edge for the given path ("${a}" - "${l}").`);
      } else {
        if (n !== "mixed") throw new ce(`Graph.${t}: calling this method with only a key (vs. a source and target) does not make sense since an edge with this key could have the other type.`);
        if (r = "" + r, s = this._edges.get(r), !s) throw new Y(`Graph.${t}: could not find the "${r}" edge in the graph.`);
      }
      if (typeof o != "function") throw new X(`Graph.${t}: updater should be a function.`);
      return s.attributes[i] = o(s.attributes[i]), this.emit("edgeAttributesUpdated", {
        key: s.key,
        type: "set",
        attributes: s.attributes,
        name: i
      }), this;
    };
  }
  function jE(e, t, n) {
    e.prototype[t] = function(r, i) {
      let o;
      if (this.type !== "mixed" && n !== "mixed" && n !== this.type) throw new ce(`Graph.${t}: cannot find this type of edges in your ${this.type} graph.`);
      if (arguments.length > 2) {
        if (this.multi) throw new ce(`Graph.${t}: cannot use a {source,target} combo when asking about an edge's attributes in a MultiGraph since we cannot infer the one you want information about.`);
        const s = "" + r, a = "" + i;
        if (i = arguments[2], o = nn(this, s, a, n), !o) throw new Y(`Graph.${t}: could not find an edge for the given path ("${s}" - "${a}").`);
      } else {
        if (n !== "mixed") throw new ce(`Graph.${t}: calling this method with only a key (vs. a source and target) does not make sense since an edge with this key could have the other type.`);
        if (r = "" + r, o = this._edges.get(r), !o) throw new Y(`Graph.${t}: could not find the "${r}" edge in the graph.`);
      }
      return delete o.attributes[i], this.emit("edgeAttributesUpdated", {
        key: o.key,
        type: "remove",
        attributes: o.attributes,
        name: i
      }), this;
    };
  }
  function HE(e, t, n) {
    e.prototype[t] = function(r, i) {
      let o;
      if (this.type !== "mixed" && n !== "mixed" && n !== this.type) throw new ce(`Graph.${t}: cannot find this type of edges in your ${this.type} graph.`);
      if (arguments.length > 2) {
        if (this.multi) throw new ce(`Graph.${t}: cannot use a {source,target} combo when asking about an edge's attributes in a MultiGraph since we cannot infer the one you want information about.`);
        const s = "" + r, a = "" + i;
        if (i = arguments[2], o = nn(this, s, a, n), !o) throw new Y(`Graph.${t}: could not find an edge for the given path ("${s}" - "${a}").`);
      } else {
        if (n !== "mixed") throw new ce(`Graph.${t}: calling this method with only a key (vs. a source and target) does not make sense since an edge with this key could have the other type.`);
        if (r = "" + r, o = this._edges.get(r), !o) throw new Y(`Graph.${t}: could not find the "${r}" edge in the graph.`);
      }
      if (!ht(i)) throw new X(`Graph.${t}: provided attributes are not a plain object.`);
      return o.attributes = i, this.emit("edgeAttributesUpdated", {
        key: o.key,
        type: "replace",
        attributes: o.attributes
      }), this;
    };
  }
  function WE(e, t, n) {
    e.prototype[t] = function(r, i) {
      let o;
      if (this.type !== "mixed" && n !== "mixed" && n !== this.type) throw new ce(`Graph.${t}: cannot find this type of edges in your ${this.type} graph.`);
      if (arguments.length > 2) {
        if (this.multi) throw new ce(`Graph.${t}: cannot use a {source,target} combo when asking about an edge's attributes in a MultiGraph since we cannot infer the one you want information about.`);
        const s = "" + r, a = "" + i;
        if (i = arguments[2], o = nn(this, s, a, n), !o) throw new Y(`Graph.${t}: could not find an edge for the given path ("${s}" - "${a}").`);
      } else {
        if (n !== "mixed") throw new ce(`Graph.${t}: calling this method with only a key (vs. a source and target) does not make sense since an edge with this key could have the other type.`);
        if (r = "" + r, o = this._edges.get(r), !o) throw new Y(`Graph.${t}: could not find the "${r}" edge in the graph.`);
      }
      if (!ht(i)) throw new X(`Graph.${t}: provided attributes are not a plain object.`);
      return it(o.attributes, i), this.emit("edgeAttributesUpdated", {
        key: o.key,
        type: "merge",
        attributes: o.attributes,
        data: i
      }), this;
    };
  }
  function VE(e, t, n) {
    e.prototype[t] = function(r, i) {
      let o;
      if (this.type !== "mixed" && n !== "mixed" && n !== this.type) throw new ce(`Graph.${t}: cannot find this type of edges in your ${this.type} graph.`);
      if (arguments.length > 2) {
        if (this.multi) throw new ce(`Graph.${t}: cannot use a {source,target} combo when asking about an edge's attributes in a MultiGraph since we cannot infer the one you want information about.`);
        const s = "" + r, a = "" + i;
        if (i = arguments[2], o = nn(this, s, a, n), !o) throw new Y(`Graph.${t}: could not find an edge for the given path ("${s}" - "${a}").`);
      } else {
        if (n !== "mixed") throw new ce(`Graph.${t}: calling this method with only a key (vs. a source and target) does not make sense since an edge with this key could have the other type.`);
        if (r = "" + r, o = this._edges.get(r), !o) throw new Y(`Graph.${t}: could not find the "${r}" edge in the graph.`);
      }
      if (typeof i != "function") throw new X(`Graph.${t}: provided updater is not a function.`);
      return o.attributes = i(o.attributes), this.emit("edgeAttributesUpdated", {
        key: o.key,
        type: "update",
        attributes: o.attributes
      }), this;
    };
  }
  const KE = [
    {
      name: (e) => `get${e}Attribute`,
      attacher: GE
    },
    {
      name: (e) => `get${e}Attributes`,
      attacher: UE
    },
    {
      name: (e) => `has${e}Attribute`,
      attacher: BE
    },
    {
      name: (e) => `set${e}Attribute`,
      attacher: ME
    },
    {
      name: (e) => `update${e}Attribute`,
      attacher: $E
    },
    {
      name: (e) => `remove${e}Attribute`,
      attacher: jE
    },
    {
      name: (e) => `replace${e}Attributes`,
      attacher: HE
    },
    {
      name: (e) => `merge${e}Attributes`,
      attacher: WE
    },
    {
      name: (e) => `update${e}Attributes`,
      attacher: VE
    }
  ];
  function YE(e) {
    KE.forEach(function({ name: t, attacher: n }) {
      n(e, t("Edge"), "mixed"), n(e, t("DirectedEdge"), "directed"), n(e, t("UndirectedEdge"), "undirected");
    });
  }
  const QE = [
    {
      name: "edges",
      type: "mixed"
    },
    {
      name: "inEdges",
      type: "directed",
      direction: "in"
    },
    {
      name: "outEdges",
      type: "directed",
      direction: "out"
    },
    {
      name: "inboundEdges",
      type: "mixed",
      direction: "in"
    },
    {
      name: "outboundEdges",
      type: "mixed",
      direction: "out"
    },
    {
      name: "directedEdges",
      type: "directed"
    },
    {
      name: "undirectedEdges",
      type: "undirected"
    }
  ];
  function XE(e, t, n, r) {
    let i = false;
    for (const o in t) {
      if (o === r) continue;
      const s = t[o];
      if (i = n(s.key, s.attributes, s.source.key, s.target.key, s.source.attributes, s.target.attributes, s.undirected), e && i) return s.key;
    }
  }
  function ZE(e, t, n, r) {
    let i, o, s, a = false;
    for (const l in t) if (l !== r) {
      i = t[l];
      do {
        if (o = i.source, s = i.target, a = n(i.key, i.attributes, o.key, s.key, o.attributes, s.attributes, i.undirected), e && a) return i.key;
        i = i.next;
      } while (i !== void 0);
    }
  }
  function ul(e, t) {
    const n = Object.keys(e), r = n.length;
    let i, o = 0;
    return {
      [Symbol.iterator]() {
        return this;
      },
      next() {
        do
          if (i) i = i.next;
          else {
            if (o >= r) return {
              done: true
            };
            const s = n[o++];
            if (s === t) {
              i = void 0;
              continue;
            }
            i = e[s];
          }
        while (!i);
        return {
          done: false,
          value: {
            edge: i.key,
            attributes: i.attributes,
            source: i.source.key,
            target: i.target.key,
            sourceAttributes: i.source.attributes,
            targetAttributes: i.target.attributes,
            undirected: i.undirected
          }
        };
      }
    };
  }
  function qE(e, t, n, r) {
    const i = t[n];
    if (!i) return;
    const o = i.source, s = i.target;
    if (r(i.key, i.attributes, o.key, s.key, o.attributes, s.attributes, i.undirected) && e) return i.key;
  }
  function JE(e, t, n, r) {
    let i = t[n];
    if (!i) return;
    let o = false;
    do {
      if (o = r(i.key, i.attributes, i.source.key, i.target.key, i.source.attributes, i.target.attributes, i.undirected), e && o) return i.key;
      i = i.next;
    } while (i !== void 0);
  }
  function cl(e, t) {
    let n = e[t];
    if (n.next !== void 0) return {
      [Symbol.iterator]() {
        return this;
      },
      next() {
        if (!n) return {
          done: true
        };
        const i = {
          edge: n.key,
          attributes: n.attributes,
          source: n.source.key,
          target: n.target.key,
          sourceAttributes: n.source.attributes,
          targetAttributes: n.target.attributes,
          undirected: n.undirected
        };
        return n = n.next, {
          done: false,
          value: i
        };
      }
    };
    let r = false;
    return {
      [Symbol.iterator]() {
        return this;
      },
      next() {
        return r === true ? {
          done: true
        } : (r = true, {
          done: false,
          value: {
            edge: n.key,
            attributes: n.attributes,
            source: n.source.key,
            target: n.target.key,
            sourceAttributes: n.source.attributes,
            targetAttributes: n.target.attributes,
            undirected: n.undirected
          }
        });
      }
    };
  }
  function e1(e, t) {
    if (e.size === 0) return [];
    if (t === "mixed" || t === e.type) return Array.from(e._edges.keys());
    const n = t === "undirected" ? e.undirectedSize : e.directedSize, r = new Array(n), i = t === "undirected", o = e._edges.values();
    let s = 0, a, l;
    for (; a = o.next(), a.done !== true; ) l = a.value, l.undirected === i && (r[s++] = l.key);
    return r;
  }
  function Dg(e, t, n, r) {
    if (t.size === 0) return;
    const i = n !== "mixed" && n !== t.type, o = n === "undirected";
    let s, a, l = false;
    const c = t._edges.values();
    for (; s = c.next(), s.done !== true; ) {
      if (a = s.value, i && a.undirected !== o) continue;
      const { key: h, attributes: f, source: p, target: y } = a;
      if (l = r(h, f, p.key, y.key, p.attributes, y.attributes, a.undirected), e && l) return h;
    }
  }
  function t1(e, t) {
    if (e.size === 0) return ki();
    const n = t !== "mixed" && t !== e.type, r = t === "undirected", i = e._edges.values();
    return {
      [Symbol.iterator]() {
        return this;
      },
      next() {
        let o, s;
        for (; ; ) {
          if (o = i.next(), o.done) return o;
          if (s = o.value, !(n && s.undirected !== r)) break;
        }
        return {
          value: {
            edge: s.key,
            attributes: s.attributes,
            source: s.source.key,
            target: s.target.key,
            sourceAttributes: s.source.attributes,
            targetAttributes: s.target.attributes,
            undirected: s.undirected
          },
          done: false
        };
      }
    };
  }
  function vc(e, t, n, r, i, o) {
    const s = t ? ZE : XE;
    let a;
    if (n !== "undirected" && (r !== "out" && (a = s(e, i.in, o), e && a) || r !== "in" && (a = s(e, i.out, o, r ? void 0 : i.key), e && a)) || n !== "directed" && (a = s(e, i.undirected, o), e && a)) return a;
  }
  function n1(e, t, n, r) {
    const i = [];
    return vc(false, e, t, n, r, function(o) {
      i.push(o);
    }), i;
  }
  function r1(e, t, n) {
    let r = ki();
    return e !== "undirected" && (t !== "out" && typeof n.in < "u" && (r = jn(r, ul(n.in))), t !== "in" && typeof n.out < "u" && (r = jn(r, ul(n.out, t ? void 0 : n.key)))), e !== "directed" && typeof n.undirected < "u" && (r = jn(r, ul(n.undirected))), r;
  }
  function yc(e, t, n, r, i, o, s) {
    const a = n ? JE : qE;
    let l;
    if (t !== "undirected" && (typeof i.in < "u" && r !== "out" && (l = a(e, i.in, o, s), e && l) || typeof i.out < "u" && r !== "in" && (r || i.key !== o) && (l = a(e, i.out, o, s), e && l)) || t !== "directed" && typeof i.undirected < "u" && (l = a(e, i.undirected, o, s), e && l)) return l;
  }
  function i1(e, t, n, r, i) {
    const o = [];
    return yc(false, e, t, n, r, i, function(s) {
      o.push(s);
    }), o;
  }
  function o1(e, t, n, r) {
    let i = ki();
    return e !== "undirected" && (typeof n.in < "u" && t !== "out" && r in n.in && (i = jn(i, cl(n.in, r))), typeof n.out < "u" && t !== "in" && r in n.out && (t || n.key !== r) && (i = jn(i, cl(n.out, r)))), e !== "directed" && typeof n.undirected < "u" && r in n.undirected && (i = jn(i, cl(n.undirected, r))), i;
  }
  function s1(e, t) {
    const { name: n, type: r, direction: i } = t;
    e.prototype[n] = function(o, s) {
      if (r !== "mixed" && this.type !== "mixed" && r !== this.type) return [];
      if (!arguments.length) return e1(this, r);
      if (arguments.length === 1) {
        o = "" + o;
        const a = this._nodes.get(o);
        if (typeof a > "u") throw new Y(`Graph.${n}: could not find the "${o}" node in the graph.`);
        return n1(this.multi, r === "mixed" ? this.type : r, i, a);
      }
      if (arguments.length === 2) {
        o = "" + o, s = "" + s;
        const a = this._nodes.get(o);
        if (!a) throw new Y(`Graph.${n}:  could not find the "${o}" source node in the graph.`);
        if (!this._nodes.has(s)) throw new Y(`Graph.${n}:  could not find the "${s}" target node in the graph.`);
        return i1(r, this.multi, i, a, s);
      }
      throw new X(`Graph.${n}: too many arguments (expecting 0, 1 or 2 and got ${arguments.length}).`);
    };
  }
  function a1(e, t) {
    const { name: n, type: r, direction: i } = t, o = "forEach" + n[0].toUpperCase() + n.slice(1, -1);
    e.prototype[o] = function(c, h, f) {
      if (!(r !== "mixed" && this.type !== "mixed" && r !== this.type)) {
        if (arguments.length === 1) return f = c, Dg(false, this, r, f);
        if (arguments.length === 2) {
          c = "" + c, f = h;
          const p = this._nodes.get(c);
          if (typeof p > "u") throw new Y(`Graph.${o}: could not find the "${c}" node in the graph.`);
          return vc(false, this.multi, r === "mixed" ? this.type : r, i, p, f);
        }
        if (arguments.length === 3) {
          c = "" + c, h = "" + h;
          const p = this._nodes.get(c);
          if (!p) throw new Y(`Graph.${o}:  could not find the "${c}" source node in the graph.`);
          if (!this._nodes.has(h)) throw new Y(`Graph.${o}:  could not find the "${h}" target node in the graph.`);
          return yc(false, r, this.multi, i, p, h, f);
        }
        throw new X(`Graph.${o}: too many arguments (expecting 1, 2 or 3 and got ${arguments.length}).`);
      }
    };
    const s = "map" + n[0].toUpperCase() + n.slice(1);
    e.prototype[s] = function() {
      const c = Array.prototype.slice.call(arguments), h = c.pop();
      let f;
      if (c.length === 0) {
        let p = 0;
        r !== "directed" && (p += this.undirectedSize), r !== "undirected" && (p += this.directedSize), f = new Array(p);
        let y = 0;
        c.push((k, b, I, _, m, v, E) => {
          f[y++] = h(k, b, I, _, m, v, E);
        });
      } else f = [], c.push((p, y, k, b, I, _, m) => {
        f.push(h(p, y, k, b, I, _, m));
      });
      return this[o].apply(this, c), f;
    };
    const a = "filter" + n[0].toUpperCase() + n.slice(1);
    e.prototype[a] = function() {
      const c = Array.prototype.slice.call(arguments), h = c.pop(), f = [];
      return c.push((p, y, k, b, I, _, m) => {
        h(p, y, k, b, I, _, m) && f.push(p);
      }), this[o].apply(this, c), f;
    };
    const l = "reduce" + n[0].toUpperCase() + n.slice(1);
    e.prototype[l] = function() {
      let c = Array.prototype.slice.call(arguments);
      if (c.length < 2 || c.length > 4) throw new X(`Graph.${l}: invalid number of arguments (expecting 2, 3 or 4 and got ${c.length}).`);
      if (typeof c[c.length - 1] == "function" && typeof c[c.length - 2] != "function") throw new X(`Graph.${l}: missing initial value. You must provide it because the callback takes more than one argument and we cannot infer the initial value from the first iteration, as you could with a simple array.`);
      let h, f;
      c.length === 2 ? (h = c[0], f = c[1], c = []) : c.length === 3 ? (h = c[1], f = c[2], c = [
        c[0]
      ]) : c.length === 4 && (h = c[2], f = c[3], c = [
        c[0],
        c[1]
      ]);
      let p = f;
      return c.push((y, k, b, I, _, m, v) => {
        p = h(p, y, k, b, I, _, m, v);
      }), this[o].apply(this, c), p;
    };
  }
  function l1(e, t) {
    const { name: n, type: r, direction: i } = t, o = "find" + n[0].toUpperCase() + n.slice(1, -1);
    e.prototype[o] = function(l, c, h) {
      if (r !== "mixed" && this.type !== "mixed" && r !== this.type) return false;
      if (arguments.length === 1) return h = l, Dg(true, this, r, h);
      if (arguments.length === 2) {
        l = "" + l, h = c;
        const f = this._nodes.get(l);
        if (typeof f > "u") throw new Y(`Graph.${o}: could not find the "${l}" node in the graph.`);
        return vc(true, this.multi, r === "mixed" ? this.type : r, i, f, h);
      }
      if (arguments.length === 3) {
        l = "" + l, c = "" + c;
        const f = this._nodes.get(l);
        if (!f) throw new Y(`Graph.${o}:  could not find the "${l}" source node in the graph.`);
        if (!this._nodes.has(c)) throw new Y(`Graph.${o}:  could not find the "${c}" target node in the graph.`);
        return yc(true, r, this.multi, i, f, c, h);
      }
      throw new X(`Graph.${o}: too many arguments (expecting 1, 2 or 3 and got ${arguments.length}).`);
    };
    const s = "some" + n[0].toUpperCase() + n.slice(1, -1);
    e.prototype[s] = function() {
      const l = Array.prototype.slice.call(arguments), c = l.pop();
      return l.push((f, p, y, k, b, I, _) => c(f, p, y, k, b, I, _)), !!this[o].apply(this, l);
    };
    const a = "every" + n[0].toUpperCase() + n.slice(1, -1);
    e.prototype[a] = function() {
      const l = Array.prototype.slice.call(arguments), c = l.pop();
      return l.push((f, p, y, k, b, I, _) => !c(f, p, y, k, b, I, _)), !this[o].apply(this, l);
    };
  }
  function u1(e, t) {
    const { name: n, type: r, direction: i } = t, o = n.slice(0, -1) + "Entries";
    e.prototype[o] = function(s, a) {
      if (r !== "mixed" && this.type !== "mixed" && r !== this.type) return ki();
      if (!arguments.length) return t1(this, r);
      if (arguments.length === 1) {
        s = "" + s;
        const l = this._nodes.get(s);
        if (!l) throw new Y(`Graph.${o}: could not find the "${s}" node in the graph.`);
        return r1(r, i, l);
      }
      if (arguments.length === 2) {
        s = "" + s, a = "" + a;
        const l = this._nodes.get(s);
        if (!l) throw new Y(`Graph.${o}:  could not find the "${s}" source node in the graph.`);
        if (!this._nodes.has(a)) throw new Y(`Graph.${o}:  could not find the "${a}" target node in the graph.`);
        return o1(r, i, l, a);
      }
      throw new X(`Graph.${o}: too many arguments (expecting 0, 1 or 2 and got ${arguments.length}).`);
    };
  }
  function c1(e) {
    QE.forEach((t) => {
      s1(e, t), a1(e, t), l1(e, t), u1(e, t);
    });
  }
  const d1 = [
    {
      name: "neighbors",
      type: "mixed"
    },
    {
      name: "inNeighbors",
      type: "directed",
      direction: "in"
    },
    {
      name: "outNeighbors",
      type: "directed",
      direction: "out"
    },
    {
      name: "inboundNeighbors",
      type: "mixed",
      direction: "in"
    },
    {
      name: "outboundNeighbors",
      type: "mixed",
      direction: "out"
    },
    {
      name: "directedNeighbors",
      type: "directed"
    },
    {
      name: "undirectedNeighbors",
      type: "undirected"
    }
  ];
  function ka() {
    this.A = null, this.B = null;
  }
  ka.prototype.wrap = function(e) {
    this.A === null ? this.A = e : this.B === null && (this.B = e);
  };
  ka.prototype.has = function(e) {
    return this.A !== null && e in this.A || this.B !== null && e in this.B;
  };
  function Mi(e, t, n, r, i) {
    for (const o in r) {
      const s = r[o], a = s.source, l = s.target, c = a === n ? l : a;
      if (t && t.has(c.key)) continue;
      const h = i(c.key, c.attributes);
      if (e && h) return c.key;
    }
  }
  function wc(e, t, n, r, i) {
    if (t !== "mixed") {
      if (t === "undirected") return Mi(e, null, r, r.undirected, i);
      if (typeof n == "string") return Mi(e, null, r, r[n], i);
    }
    const o = new ka();
    let s;
    if (t !== "undirected") {
      if (n !== "out") {
        if (s = Mi(e, null, r, r.in, i), e && s) return s;
        o.wrap(r.in);
      }
      if (n !== "in") {
        if (s = Mi(e, o, r, r.out, i), e && s) return s;
        o.wrap(r.out);
      }
    }
    if (t !== "directed" && (s = Mi(e, o, r, r.undirected, i), e && s)) return s;
  }
  function f1(e, t, n) {
    if (e !== "mixed") {
      if (e === "undirected") return Object.keys(n.undirected);
      if (typeof t == "string") return Object.keys(n[t]);
    }
    const r = [];
    return wc(false, e, t, n, function(i) {
      r.push(i);
    }), r;
  }
  function $i(e, t, n) {
    const r = Object.keys(n), i = r.length;
    let o = 0;
    return {
      [Symbol.iterator]() {
        return this;
      },
      next() {
        let s = null;
        do {
          if (o >= i) return e && e.wrap(n), {
            done: true
          };
          const a = n[r[o++]], l = a.source, c = a.target;
          if (s = l === t ? c : l, e && e.has(s.key)) {
            s = null;
            continue;
          }
        } while (s === null);
        return {
          done: false,
          value: {
            neighbor: s.key,
            attributes: s.attributes
          }
        };
      }
    };
  }
  function h1(e, t, n) {
    if (e !== "mixed") {
      if (e === "undirected") return $i(null, n, n.undirected);
      if (typeof t == "string") return $i(null, n, n[t]);
    }
    let r = ki();
    const i = new ka();
    return e !== "undirected" && (t !== "out" && (r = jn(r, $i(i, n, n.in))), t !== "in" && (r = jn(r, $i(i, n, n.out)))), e !== "directed" && (r = jn(r, $i(i, n, n.undirected))), r;
  }
  function p1(e, t) {
    const { name: n, type: r, direction: i } = t;
    e.prototype[n] = function(o) {
      if (r !== "mixed" && this.type !== "mixed" && r !== this.type) return [];
      o = "" + o;
      const s = this._nodes.get(o);
      if (typeof s > "u") throw new Y(`Graph.${n}: could not find the "${o}" node in the graph.`);
      return f1(r === "mixed" ? this.type : r, i, s);
    };
  }
  function g1(e, t) {
    const { name: n, type: r, direction: i } = t, o = "forEach" + n[0].toUpperCase() + n.slice(1, -1);
    e.prototype[o] = function(c, h) {
      if (r !== "mixed" && this.type !== "mixed" && r !== this.type) return;
      c = "" + c;
      const f = this._nodes.get(c);
      if (typeof f > "u") throw new Y(`Graph.${o}: could not find the "${c}" node in the graph.`);
      wc(false, r === "mixed" ? this.type : r, i, f, h);
    };
    const s = "map" + n[0].toUpperCase() + n.slice(1);
    e.prototype[s] = function(c, h) {
      const f = [];
      return this[o](c, (p, y) => {
        f.push(h(p, y));
      }), f;
    };
    const a = "filter" + n[0].toUpperCase() + n.slice(1);
    e.prototype[a] = function(c, h) {
      const f = [];
      return this[o](c, (p, y) => {
        h(p, y) && f.push(p);
      }), f;
    };
    const l = "reduce" + n[0].toUpperCase() + n.slice(1);
    e.prototype[l] = function(c, h, f) {
      if (arguments.length < 3) throw new X(`Graph.${l}: missing initial value. You must provide it because the callback takes more than one argument and we cannot infer the initial value from the first iteration, as you could with a simple array.`);
      let p = f;
      return this[o](c, (y, k) => {
        p = h(p, y, k);
      }), p;
    };
  }
  function m1(e, t) {
    const { name: n, type: r, direction: i } = t, o = n[0].toUpperCase() + n.slice(1, -1), s = "find" + o;
    e.prototype[s] = function(c, h) {
      if (r !== "mixed" && this.type !== "mixed" && r !== this.type) return;
      c = "" + c;
      const f = this._nodes.get(c);
      if (typeof f > "u") throw new Y(`Graph.${s}: could not find the "${c}" node in the graph.`);
      return wc(true, r === "mixed" ? this.type : r, i, f, h);
    };
    const a = "some" + o;
    e.prototype[a] = function(c, h) {
      return !!this[s](c, h);
    };
    const l = "every" + o;
    e.prototype[l] = function(c, h) {
      return !this[s](c, (p, y) => !h(p, y));
    };
  }
  function v1(e, t) {
    const { name: n, type: r, direction: i } = t, o = n.slice(0, -1) + "Entries";
    e.prototype[o] = function(s) {
      if (r !== "mixed" && this.type !== "mixed" && r !== this.type) return ki();
      s = "" + s;
      const a = this._nodes.get(s);
      if (typeof a > "u") throw new Y(`Graph.${o}: could not find the "${s}" node in the graph.`);
      return h1(r === "mixed" ? this.type : r, i, a);
    };
  }
  function y1(e) {
    d1.forEach((t) => {
      p1(e, t), g1(e, t), m1(e, t), v1(e, t);
    });
  }
  function os(e, t, n, r, i) {
    const o = r._nodes.values(), s = r.type;
    let a, l, c, h, f, p;
    for (; a = o.next(), a.done !== true; ) {
      let y = false;
      if (l = a.value, s !== "undirected") {
        h = l.out;
        for (c in h) {
          f = h[c];
          do
            p = f.target, y = true, i(l.key, p.key, l.attributes, p.attributes, f.key, f.attributes, f.undirected), f = f.next;
          while (f);
        }
      }
      if (s !== "directed") {
        h = l.undirected;
        for (c in h) if (!(t && l.key > c)) {
          f = h[c];
          do
            p = f.target, p.key !== c && (p = f.source), y = true, i(l.key, p.key, l.attributes, p.attributes, f.key, f.attributes, f.undirected), f = f.next;
          while (f);
        }
      }
      n && !y && i(l.key, null, l.attributes, null, null, null, null);
    }
  }
  function w1(e, t) {
    const n = {
      key: e
    };
    return xg(t.attributes) || (n.attributes = it({}, t.attributes)), n;
  }
  function E1(e, t, n) {
    const r = {
      key: t,
      source: n.source.key,
      target: n.target.key
    };
    return xg(n.attributes) || (r.attributes = it({}, n.attributes)), e === "mixed" && n.undirected && (r.undirected = true), r;
  }
  function S1(e) {
    if (!ht(e)) throw new X('Graph.import: invalid serialized node. A serialized node should be a plain object with at least a "key" property.');
    if (!("key" in e)) throw new X("Graph.import: serialized node is missing its key.");
    if ("attributes" in e && (!ht(e.attributes) || e.attributes === null)) throw new X("Graph.import: invalid attributes. Attributes should be a plain object, null or omitted.");
  }
  function _1(e) {
    if (!ht(e)) throw new X('Graph.import: invalid serialized edge. A serialized edge should be a plain object with at least a "source" & "target" property.');
    if (!("source" in e)) throw new X("Graph.import: serialized edge is missing its source.");
    if (!("target" in e)) throw new X("Graph.import: serialized edge is missing its target.");
    if ("attributes" in e && (!ht(e.attributes) || e.attributes === null)) throw new X("Graph.import: invalid attributes. Attributes should be a plain object, null or omitted.");
    if ("undirected" in e && typeof e.undirected != "boolean") throw new X("Graph.import: invalid undirectedness information. Undirected should be boolean or omitted.");
  }
  const k1 = xE(), b1 = /* @__PURE__ */ new Set([
    "directed",
    "undirected",
    "mixed"
  ]), gf = /* @__PURE__ */ new Set([
    "domain",
    "_events",
    "_eventsCount",
    "_maxListeners"
  ]), x1 = [
    {
      name: (e) => `${e}Edge`,
      generateKey: true
    },
    {
      name: (e) => `${e}DirectedEdge`,
      generateKey: true,
      type: "directed"
    },
    {
      name: (e) => `${e}UndirectedEdge`,
      generateKey: true,
      type: "undirected"
    },
    {
      name: (e) => `${e}EdgeWithKey`
    },
    {
      name: (e) => `${e}DirectedEdgeWithKey`,
      type: "directed"
    },
    {
      name: (e) => `${e}UndirectedEdgeWithKey`,
      type: "undirected"
    }
  ], C1 = {
    allowSelfLoops: true,
    multi: false,
    type: "mixed"
  };
  function T1(e, t, n) {
    if (n && !ht(n)) throw new X(`Graph.addNode: invalid attributes. Expecting an object but got "${n}"`);
    if (t = "" + t, n = n || {}, e._nodes.has(t)) throw new ce(`Graph.addNode: the "${t}" node already exist in the graph.`);
    const r = new e.NodeDataClass(t, n);
    return e._nodes.set(t, r), e.emit("nodeAdded", {
      key: t,
      attributes: n
    }), r;
  }
  function mf(e, t, n) {
    const r = new e.NodeDataClass(t, n);
    return e._nodes.set(t, r), e.emit("nodeAdded", {
      key: t,
      attributes: n
    }), r;
  }
  function Pg(e, t, n, r, i, o, s, a) {
    if (!r && e.type === "undirected") throw new ce(`Graph.${t}: you cannot add a directed edge to an undirected graph. Use the #.addEdge or #.addUndirectedEdge instead.`);
    if (r && e.type === "directed") throw new ce(`Graph.${t}: you cannot add an undirected edge to a directed graph. Use the #.addEdge or #.addDirectedEdge instead.`);
    if (a && !ht(a)) throw new X(`Graph.${t}: invalid attributes. Expecting an object but got "${a}"`);
    if (o = "" + o, s = "" + s, a = a || {}, !e.allowSelfLoops && o === s) throw new ce(`Graph.${t}: source & target are the same ("${o}"), thus creating a loop explicitly forbidden by this graph 'allowSelfLoops' option set to false.`);
    const l = e._nodes.get(o), c = e._nodes.get(s);
    if (!l) throw new Y(`Graph.${t}: source node "${o}" not found.`);
    if (!c) throw new Y(`Graph.${t}: target node "${s}" not found.`);
    const h = {
      key: null,
      undirected: r,
      source: o,
      target: s,
      attributes: a
    };
    if (n) i = e._edgeKeyGenerator();
    else if (i = "" + i, e._edges.has(i)) throw new ce(`Graph.${t}: the "${i}" edge already exists in the graph.`);
    if (!e.multi && (r ? typeof l.undirected[s] < "u" : typeof l.out[s] < "u")) throw new ce(`Graph.${t}: an edge linking "${o}" to "${s}" already exists. If you really want to add multiple edges linking those nodes, you should create a multi graph by using the 'multi' option.`);
    const f = new bi(r, i, l, c, a);
    e._edges.set(i, f);
    const p = o === s;
    return r ? (l.undirectedDegree++, c.undirectedDegree++, p && (l.undirectedLoops++, e._undirectedSelfLoopCount++)) : (l.outDegree++, c.inDegree++, p && (l.directedLoops++, e._directedSelfLoopCount++)), e.multi ? f.attachMulti() : f.attach(), r ? e._undirectedSize++ : e._directedSize++, h.key = i, e.emit("edgeAdded", h), i;
  }
  function R1(e, t, n, r, i, o, s, a, l) {
    if (!r && e.type === "undirected") throw new ce(`Graph.${t}: you cannot merge/update a directed edge to an undirected graph. Use the #.mergeEdge/#.updateEdge or #.addUndirectedEdge instead.`);
    if (r && e.type === "directed") throw new ce(`Graph.${t}: you cannot merge/update an undirected edge to a directed graph. Use the #.mergeEdge/#.updateEdge or #.addDirectedEdge instead.`);
    if (a) {
      if (l) {
        if (typeof a != "function") throw new X(`Graph.${t}: invalid updater function. Expecting a function but got "${a}"`);
      } else if (!ht(a)) throw new X(`Graph.${t}: invalid attributes. Expecting an object but got "${a}"`);
    }
    o = "" + o, s = "" + s;
    let c;
    if (l && (c = a, a = void 0), !e.allowSelfLoops && o === s) throw new ce(`Graph.${t}: source & target are the same ("${o}"), thus creating a loop explicitly forbidden by this graph 'allowSelfLoops' option set to false.`);
    let h = e._nodes.get(o), f = e._nodes.get(s), p, y;
    if (!n && (p = e._edges.get(i), p)) {
      if ((p.source.key !== o || p.target.key !== s) && (!r || p.source.key !== s || p.target.key !== o)) throw new ce(`Graph.${t}: inconsistency detected when attempting to merge the "${i}" edge with "${o}" source & "${s}" target vs. ("${p.source.key}", "${p.target.key}").`);
      y = p;
    }
    if (!y && !e.multi && h && (y = r ? h.undirected[s] : h.out[s]), y) {
      const m = [
        y.key,
        false,
        false,
        false
      ];
      if (l ? !c : !a) return m;
      if (l) {
        const v = y.attributes;
        y.attributes = c(v), e.emit("edgeAttributesUpdated", {
          type: "replace",
          key: y.key,
          attributes: y.attributes
        });
      } else it(y.attributes, a), e.emit("edgeAttributesUpdated", {
        type: "merge",
        key: y.key,
        attributes: y.attributes,
        data: a
      });
      return m;
    }
    a = a || {}, l && c && (a = c(a));
    const k = {
      key: null,
      undirected: r,
      source: o,
      target: s,
      attributes: a
    };
    if (n) i = e._edgeKeyGenerator();
    else if (i = "" + i, e._edges.has(i)) throw new ce(`Graph.${t}: the "${i}" edge already exists in the graph.`);
    let b = false, I = false;
    h || (h = mf(e, o, {}), b = true, o === s && (f = h, I = true)), f || (f = mf(e, s, {}), I = true), p = new bi(r, i, h, f, a), e._edges.set(i, p);
    const _ = o === s;
    return r ? (h.undirectedDegree++, f.undirectedDegree++, _ && (h.undirectedLoops++, e._undirectedSelfLoopCount++)) : (h.outDegree++, f.inDegree++, _ && (h.directedLoops++, e._directedSelfLoopCount++)), e.multi ? p.attachMulti() : p.attach(), r ? e._undirectedSize++ : e._directedSize++, k.key = i, e.emit("edgeAdded", k), [
      i,
      true,
      b,
      I
    ];
  }
  function Mr(e, t) {
    e._edges.delete(t.key);
    const { source: n, target: r, attributes: i } = t, o = t.undirected, s = n === r;
    o ? (n.undirectedDegree--, r.undirectedDegree--, s && (n.undirectedLoops--, e._undirectedSelfLoopCount--)) : (n.outDegree--, r.inDegree--, s && (n.directedLoops--, e._directedSelfLoopCount--)), e.multi ? t.detachMulti() : t.detach(), o ? e._undirectedSize-- : e._directedSize--, e.emit("edgeDropped", {
      key: t.key,
      attributes: i,
      source: n.key,
      target: r.key,
      undirected: o
    });
  }
  class Pe extends _g.EventEmitter {
    constructor(t) {
      if (super(), t = it({}, C1, t), typeof t.multi != "boolean") throw new X(`Graph.constructor: invalid 'multi' option. Expecting a boolean but got "${t.multi}".`);
      if (!b1.has(t.type)) throw new X(`Graph.constructor: invalid 'type' option. Should be one of "mixed", "directed" or "undirected" but got "${t.type}".`);
      if (typeof t.allowSelfLoops != "boolean") throw new X(`Graph.constructor: invalid 'allowSelfLoops' option. Expecting a boolean but got "${t.allowSelfLoops}".`);
      const n = t.type === "mixed" ? Cg : t.type === "directed" ? Tg : Rg;
      Qt(this, "NodeDataClass", n);
      const r = "geid_" + k1() + "_";
      let i = 0;
      const o = () => {
        let s;
        do
          s = r + i++;
        while (this._edges.has(s));
        return s;
      };
      Qt(this, "_attributes", {}), Qt(this, "_nodes", /* @__PURE__ */ new Map()), Qt(this, "_edges", /* @__PURE__ */ new Map()), Qt(this, "_directedSize", 0), Qt(this, "_undirectedSize", 0), Qt(this, "_directedSelfLoopCount", 0), Qt(this, "_undirectedSelfLoopCount", 0), Qt(this, "_edgeKeyGenerator", o), Qt(this, "_options", t), gf.forEach((s) => Qt(this, s, this[s])), fn(this, "order", () => this._nodes.size), fn(this, "size", () => this._edges.size), fn(this, "directedSize", () => this._directedSize), fn(this, "undirectedSize", () => this._undirectedSize), fn(this, "selfLoopCount", () => this._directedSelfLoopCount + this._undirectedSelfLoopCount), fn(this, "directedSelfLoopCount", () => this._directedSelfLoopCount), fn(this, "undirectedSelfLoopCount", () => this._undirectedSelfLoopCount), fn(this, "multi", this._options.multi), fn(this, "type", this._options.type), fn(this, "allowSelfLoops", this._options.allowSelfLoops), fn(this, "implementation", () => "graphology");
    }
    _resetInstanceCounters() {
      this._directedSize = 0, this._undirectedSize = 0, this._directedSelfLoopCount = 0, this._undirectedSelfLoopCount = 0;
    }
    hasNode(t) {
      return this._nodes.has("" + t);
    }
    hasDirectedEdge(t, n) {
      if (this.type === "undirected") return false;
      if (arguments.length === 1) {
        const r = "" + t, i = this._edges.get(r);
        return !!i && !i.undirected;
      } else if (arguments.length === 2) {
        t = "" + t, n = "" + n;
        const r = this._nodes.get(t);
        return r ? r.out.hasOwnProperty(n) : false;
      }
      throw new X(`Graph.hasDirectedEdge: invalid arity (${arguments.length}, instead of 1 or 2). You can either ask for an edge id or for the existence of an edge between a source & a target.`);
    }
    hasUndirectedEdge(t, n) {
      if (this.type === "directed") return false;
      if (arguments.length === 1) {
        const r = "" + t, i = this._edges.get(r);
        return !!i && i.undirected;
      } else if (arguments.length === 2) {
        t = "" + t, n = "" + n;
        const r = this._nodes.get(t);
        return r ? r.undirected.hasOwnProperty(n) : false;
      }
      throw new X(`Graph.hasDirectedEdge: invalid arity (${arguments.length}, instead of 1 or 2). You can either ask for an edge id or for the existence of an edge between a source & a target.`);
    }
    hasEdge(t, n) {
      if (arguments.length === 1) {
        const r = "" + t;
        return this._edges.has(r);
      } else if (arguments.length === 2) {
        t = "" + t, n = "" + n;
        const r = this._nodes.get(t);
        return r ? typeof r.out < "u" && r.out.hasOwnProperty(n) || typeof r.undirected < "u" && r.undirected.hasOwnProperty(n) : false;
      }
      throw new X(`Graph.hasEdge: invalid arity (${arguments.length}, instead of 1 or 2). You can either ask for an edge id or for the existence of an edge between a source & a target.`);
    }
    directedEdge(t, n) {
      if (this.type === "undirected") return;
      if (t = "" + t, n = "" + n, this.multi) throw new ce("Graph.directedEdge: this method is irrelevant with multigraphs since there might be multiple edges between source & target. See #.directedEdges instead.");
      const r = this._nodes.get(t);
      if (!r) throw new Y(`Graph.directedEdge: could not find the "${t}" source node in the graph.`);
      if (!this._nodes.has(n)) throw new Y(`Graph.directedEdge: could not find the "${n}" target node in the graph.`);
      const i = r.out && r.out[n] || void 0;
      if (i) return i.key;
    }
    undirectedEdge(t, n) {
      if (this.type === "directed") return;
      if (t = "" + t, n = "" + n, this.multi) throw new ce("Graph.undirectedEdge: this method is irrelevant with multigraphs since there might be multiple edges between source & target. See #.undirectedEdges instead.");
      const r = this._nodes.get(t);
      if (!r) throw new Y(`Graph.undirectedEdge: could not find the "${t}" source node in the graph.`);
      if (!this._nodes.has(n)) throw new Y(`Graph.undirectedEdge: could not find the "${n}" target node in the graph.`);
      const i = r.undirected && r.undirected[n] || void 0;
      if (i) return i.key;
    }
    edge(t, n) {
      if (this.multi) throw new ce("Graph.edge: this method is irrelevant with multigraphs since there might be multiple edges between source & target. See #.edges instead.");
      t = "" + t, n = "" + n;
      const r = this._nodes.get(t);
      if (!r) throw new Y(`Graph.edge: could not find the "${t}" source node in the graph.`);
      if (!this._nodes.has(n)) throw new Y(`Graph.edge: could not find the "${n}" target node in the graph.`);
      const i = r.out && r.out[n] || r.undirected && r.undirected[n] || void 0;
      if (i) return i.key;
    }
    areDirectedNeighbors(t, n) {
      t = "" + t, n = "" + n;
      const r = this._nodes.get(t);
      if (!r) throw new Y(`Graph.areDirectedNeighbors: could not find the "${t}" node in the graph.`);
      return this.type === "undirected" ? false : n in r.in || n in r.out;
    }
    areOutNeighbors(t, n) {
      t = "" + t, n = "" + n;
      const r = this._nodes.get(t);
      if (!r) throw new Y(`Graph.areOutNeighbors: could not find the "${t}" node in the graph.`);
      return this.type === "undirected" ? false : n in r.out;
    }
    areInNeighbors(t, n) {
      t = "" + t, n = "" + n;
      const r = this._nodes.get(t);
      if (!r) throw new Y(`Graph.areInNeighbors: could not find the "${t}" node in the graph.`);
      return this.type === "undirected" ? false : n in r.in;
    }
    areUndirectedNeighbors(t, n) {
      t = "" + t, n = "" + n;
      const r = this._nodes.get(t);
      if (!r) throw new Y(`Graph.areUndirectedNeighbors: could not find the "${t}" node in the graph.`);
      return this.type === "directed" ? false : n in r.undirected;
    }
    areNeighbors(t, n) {
      t = "" + t, n = "" + n;
      const r = this._nodes.get(t);
      if (!r) throw new Y(`Graph.areNeighbors: could not find the "${t}" node in the graph.`);
      return this.type !== "undirected" && (n in r.in || n in r.out) || this.type !== "directed" && n in r.undirected;
    }
    areInboundNeighbors(t, n) {
      t = "" + t, n = "" + n;
      const r = this._nodes.get(t);
      if (!r) throw new Y(`Graph.areInboundNeighbors: could not find the "${t}" node in the graph.`);
      return this.type !== "undirected" && n in r.in || this.type !== "directed" && n in r.undirected;
    }
    areOutboundNeighbors(t, n) {
      t = "" + t, n = "" + n;
      const r = this._nodes.get(t);
      if (!r) throw new Y(`Graph.areOutboundNeighbors: could not find the "${t}" node in the graph.`);
      return this.type !== "undirected" && n in r.out || this.type !== "directed" && n in r.undirected;
    }
    inDegree(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new Y(`Graph.inDegree: could not find the "${t}" node in the graph.`);
      return this.type === "undirected" ? 0 : n.inDegree;
    }
    outDegree(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new Y(`Graph.outDegree: could not find the "${t}" node in the graph.`);
      return this.type === "undirected" ? 0 : n.outDegree;
    }
    directedDegree(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new Y(`Graph.directedDegree: could not find the "${t}" node in the graph.`);
      return this.type === "undirected" ? 0 : n.inDegree + n.outDegree;
    }
    undirectedDegree(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new Y(`Graph.undirectedDegree: could not find the "${t}" node in the graph.`);
      return this.type === "directed" ? 0 : n.undirectedDegree;
    }
    inboundDegree(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new Y(`Graph.inboundDegree: could not find the "${t}" node in the graph.`);
      let r = 0;
      return this.type !== "directed" && (r += n.undirectedDegree), this.type !== "undirected" && (r += n.inDegree), r;
    }
    outboundDegree(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new Y(`Graph.outboundDegree: could not find the "${t}" node in the graph.`);
      let r = 0;
      return this.type !== "directed" && (r += n.undirectedDegree), this.type !== "undirected" && (r += n.outDegree), r;
    }
    degree(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new Y(`Graph.degree: could not find the "${t}" node in the graph.`);
      let r = 0;
      return this.type !== "directed" && (r += n.undirectedDegree), this.type !== "undirected" && (r += n.inDegree + n.outDegree), r;
    }
    inDegreeWithoutSelfLoops(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new Y(`Graph.inDegreeWithoutSelfLoops: could not find the "${t}" node in the graph.`);
      return this.type === "undirected" ? 0 : n.inDegree - n.directedLoops;
    }
    outDegreeWithoutSelfLoops(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new Y(`Graph.outDegreeWithoutSelfLoops: could not find the "${t}" node in the graph.`);
      return this.type === "undirected" ? 0 : n.outDegree - n.directedLoops;
    }
    directedDegreeWithoutSelfLoops(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new Y(`Graph.directedDegreeWithoutSelfLoops: could not find the "${t}" node in the graph.`);
      return this.type === "undirected" ? 0 : n.inDegree + n.outDegree - n.directedLoops * 2;
    }
    undirectedDegreeWithoutSelfLoops(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new Y(`Graph.undirectedDegreeWithoutSelfLoops: could not find the "${t}" node in the graph.`);
      return this.type === "directed" ? 0 : n.undirectedDegree - n.undirectedLoops * 2;
    }
    inboundDegreeWithoutSelfLoops(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new Y(`Graph.inboundDegreeWithoutSelfLoops: could not find the "${t}" node in the graph.`);
      let r = 0, i = 0;
      return this.type !== "directed" && (r += n.undirectedDegree, i += n.undirectedLoops * 2), this.type !== "undirected" && (r += n.inDegree, i += n.directedLoops), r - i;
    }
    outboundDegreeWithoutSelfLoops(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new Y(`Graph.outboundDegreeWithoutSelfLoops: could not find the "${t}" node in the graph.`);
      let r = 0, i = 0;
      return this.type !== "directed" && (r += n.undirectedDegree, i += n.undirectedLoops * 2), this.type !== "undirected" && (r += n.outDegree, i += n.directedLoops), r - i;
    }
    degreeWithoutSelfLoops(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new Y(`Graph.degreeWithoutSelfLoops: could not find the "${t}" node in the graph.`);
      let r = 0, i = 0;
      return this.type !== "directed" && (r += n.undirectedDegree, i += n.undirectedLoops * 2), this.type !== "undirected" && (r += n.inDegree + n.outDegree, i += n.directedLoops * 2), r - i;
    }
    source(t) {
      t = "" + t;
      const n = this._edges.get(t);
      if (!n) throw new Y(`Graph.source: could not find the "${t}" edge in the graph.`);
      return n.source.key;
    }
    target(t) {
      t = "" + t;
      const n = this._edges.get(t);
      if (!n) throw new Y(`Graph.target: could not find the "${t}" edge in the graph.`);
      return n.target.key;
    }
    extremities(t) {
      t = "" + t;
      const n = this._edges.get(t);
      if (!n) throw new Y(`Graph.extremities: could not find the "${t}" edge in the graph.`);
      return [
        n.source.key,
        n.target.key
      ];
    }
    opposite(t, n) {
      t = "" + t, n = "" + n;
      const r = this._edges.get(n);
      if (!r) throw new Y(`Graph.opposite: could not find the "${n}" edge in the graph.`);
      const i = r.source.key, o = r.target.key;
      if (t === i) return o;
      if (t === o) return i;
      throw new Y(`Graph.opposite: the "${t}" node is not attached to the "${n}" edge (${i}, ${o}).`);
    }
    hasExtremity(t, n) {
      t = "" + t, n = "" + n;
      const r = this._edges.get(t);
      if (!r) throw new Y(`Graph.hasExtremity: could not find the "${t}" edge in the graph.`);
      return r.source.key === n || r.target.key === n;
    }
    isUndirected(t) {
      t = "" + t;
      const n = this._edges.get(t);
      if (!n) throw new Y(`Graph.isUndirected: could not find the "${t}" edge in the graph.`);
      return n.undirected;
    }
    isDirected(t) {
      t = "" + t;
      const n = this._edges.get(t);
      if (!n) throw new Y(`Graph.isDirected: could not find the "${t}" edge in the graph.`);
      return !n.undirected;
    }
    isSelfLoop(t) {
      t = "" + t;
      const n = this._edges.get(t);
      if (!n) throw new Y(`Graph.isSelfLoop: could not find the "${t}" edge in the graph.`);
      return n.source === n.target;
    }
    addNode(t, n) {
      return T1(this, t, n).key;
    }
    mergeNode(t, n) {
      if (n && !ht(n)) throw new X(`Graph.mergeNode: invalid attributes. Expecting an object but got "${n}"`);
      t = "" + t, n = n || {};
      let r = this._nodes.get(t);
      return r ? (n && (it(r.attributes, n), this.emit("nodeAttributesUpdated", {
        type: "merge",
        key: t,
        attributes: r.attributes,
        data: n
      })), [
        t,
        false
      ]) : (r = new this.NodeDataClass(t, n), this._nodes.set(t, r), this.emit("nodeAdded", {
        key: t,
        attributes: n
      }), [
        t,
        true
      ]);
    }
    updateNode(t, n) {
      if (n && typeof n != "function") throw new X(`Graph.updateNode: invalid updater function. Expecting a function but got "${n}"`);
      t = "" + t;
      let r = this._nodes.get(t);
      if (r) {
        if (n) {
          const o = r.attributes;
          r.attributes = n(o), this.emit("nodeAttributesUpdated", {
            type: "replace",
            key: t,
            attributes: r.attributes
          });
        }
        return [
          t,
          false
        ];
      }
      const i = n ? n({}) : {};
      return r = new this.NodeDataClass(t, i), this._nodes.set(t, r), this.emit("nodeAdded", {
        key: t,
        attributes: i
      }), [
        t,
        true
      ];
    }
    dropNode(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new Y(`Graph.dropNode: could not find the "${t}" node in the graph.`);
      let r;
      if (this.type !== "undirected") {
        for (const i in n.out) {
          r = n.out[i];
          do
            Mr(this, r), r = r.next;
          while (r);
        }
        for (const i in n.in) {
          r = n.in[i];
          do
            Mr(this, r), r = r.next;
          while (r);
        }
      }
      if (this.type !== "directed") for (const i in n.undirected) {
        r = n.undirected[i];
        do
          Mr(this, r), r = r.next;
        while (r);
      }
      this._nodes.delete(t), this.emit("nodeDropped", {
        key: t,
        attributes: n.attributes
      });
    }
    dropEdge(t) {
      let n;
      if (arguments.length > 1) {
        const r = "" + arguments[0], i = "" + arguments[1];
        if (n = nn(this, r, i, this.type), !n) throw new Y(`Graph.dropEdge: could not find the "${r}" -> "${i}" edge in the graph.`);
      } else if (t = "" + t, n = this._edges.get(t), !n) throw new Y(`Graph.dropEdge: could not find the "${t}" edge in the graph.`);
      return Mr(this, n), this;
    }
    dropDirectedEdge(t, n) {
      if (arguments.length < 2) throw new ce("Graph.dropDirectedEdge: it does not make sense to try and drop a directed edge by key. What if the edge with this key is undirected? Use #.dropEdge for this purpose instead.");
      if (this.multi) throw new ce("Graph.dropDirectedEdge: cannot use a {source,target} combo when dropping an edge in a MultiGraph since we cannot infer the one you want to delete as there could be multiple ones.");
      t = "" + t, n = "" + n;
      const r = nn(this, t, n, "directed");
      if (!r) throw new Y(`Graph.dropDirectedEdge: could not find a "${t}" -> "${n}" edge in the graph.`);
      return Mr(this, r), this;
    }
    dropUndirectedEdge(t, n) {
      if (arguments.length < 2) throw new ce("Graph.dropUndirectedEdge: it does not make sense to drop a directed edge by key. What if the edge with this key is undirected? Use #.dropEdge for this purpose instead.");
      if (this.multi) throw new ce("Graph.dropUndirectedEdge: cannot use a {source,target} combo when dropping an edge in a MultiGraph since we cannot infer the one you want to delete as there could be multiple ones.");
      const r = nn(this, t, n, "undirected");
      if (!r) throw new Y(`Graph.dropUndirectedEdge: could not find a "${t}" -> "${n}" edge in the graph.`);
      return Mr(this, r), this;
    }
    clear() {
      this._edges.clear(), this._nodes.clear(), this._resetInstanceCounters(), this.emit("cleared");
    }
    clearEdges() {
      const t = this._nodes.values();
      let n;
      for (; n = t.next(), n.done !== true; ) n.value.clear();
      this._edges.clear(), this._resetInstanceCounters(), this.emit("edgesCleared");
    }
    getAttribute(t) {
      return this._attributes[t];
    }
    getAttributes() {
      return this._attributes;
    }
    hasAttribute(t) {
      return this._attributes.hasOwnProperty(t);
    }
    setAttribute(t, n) {
      return this._attributes[t] = n, this.emit("attributesUpdated", {
        type: "set",
        attributes: this._attributes,
        name: t
      }), this;
    }
    updateAttribute(t, n) {
      if (typeof n != "function") throw new X("Graph.updateAttribute: updater should be a function.");
      const r = this._attributes[t];
      return this._attributes[t] = n(r), this.emit("attributesUpdated", {
        type: "set",
        attributes: this._attributes,
        name: t
      }), this;
    }
    removeAttribute(t) {
      return delete this._attributes[t], this.emit("attributesUpdated", {
        type: "remove",
        attributes: this._attributes,
        name: t
      }), this;
    }
    replaceAttributes(t) {
      if (!ht(t)) throw new X("Graph.replaceAttributes: provided attributes are not a plain object.");
      return this._attributes = t, this.emit("attributesUpdated", {
        type: "replace",
        attributes: this._attributes
      }), this;
    }
    mergeAttributes(t) {
      if (!ht(t)) throw new X("Graph.mergeAttributes: provided attributes are not a plain object.");
      return it(this._attributes, t), this.emit("attributesUpdated", {
        type: "merge",
        attributes: this._attributes,
        data: t
      }), this;
    }
    updateAttributes(t) {
      if (typeof t != "function") throw new X("Graph.updateAttributes: provided updater is not a function.");
      return this._attributes = t(this._attributes), this.emit("attributesUpdated", {
        type: "update",
        attributes: this._attributes
      }), this;
    }
    updateEachNodeAttributes(t, n) {
      if (typeof t != "function") throw new X("Graph.updateEachNodeAttributes: expecting an updater function.");
      if (n && !pf(n)) throw new X("Graph.updateEachNodeAttributes: invalid hints. Expecting an object having the following shape: {attributes?: [string]}");
      const r = this._nodes.values();
      let i, o;
      for (; i = r.next(), i.done !== true; ) o = i.value, o.attributes = t(o.key, o.attributes);
      this.emit("eachNodeAttributesUpdated", {
        hints: n || null
      });
    }
    updateEachEdgeAttributes(t, n) {
      if (typeof t != "function") throw new X("Graph.updateEachEdgeAttributes: expecting an updater function.");
      if (n && !pf(n)) throw new X("Graph.updateEachEdgeAttributes: invalid hints. Expecting an object having the following shape: {attributes?: [string]}");
      const r = this._edges.values();
      let i, o, s, a;
      for (; i = r.next(), i.done !== true; ) o = i.value, s = o.source, a = o.target, o.attributes = t(o.key, o.attributes, s.key, a.key, s.attributes, a.attributes, o.undirected);
      this.emit("eachEdgeAttributesUpdated", {
        hints: n || null
      });
    }
    forEachAdjacencyEntry(t) {
      if (typeof t != "function") throw new X("Graph.forEachAdjacencyEntry: expecting a callback.");
      os(false, false, false, this, t);
    }
    forEachAdjacencyEntryWithOrphans(t) {
      if (typeof t != "function") throw new X("Graph.forEachAdjacencyEntryWithOrphans: expecting a callback.");
      os(false, false, true, this, t);
    }
    forEachAssymetricAdjacencyEntry(t) {
      if (typeof t != "function") throw new X("Graph.forEachAssymetricAdjacencyEntry: expecting a callback.");
      os(false, true, false, this, t);
    }
    forEachAssymetricAdjacencyEntryWithOrphans(t) {
      if (typeof t != "function") throw new X("Graph.forEachAssymetricAdjacencyEntryWithOrphans: expecting a callback.");
      os(false, true, true, this, t);
    }
    nodes() {
      return Array.from(this._nodes.keys());
    }
    forEachNode(t) {
      if (typeof t != "function") throw new X("Graph.forEachNode: expecting a callback.");
      const n = this._nodes.values();
      let r, i;
      for (; r = n.next(), r.done !== true; ) i = r.value, t(i.key, i.attributes);
    }
    findNode(t) {
      if (typeof t != "function") throw new X("Graph.findNode: expecting a callback.");
      const n = this._nodes.values();
      let r, i;
      for (; r = n.next(), r.done !== true; ) if (i = r.value, t(i.key, i.attributes)) return i.key;
    }
    mapNodes(t) {
      if (typeof t != "function") throw new X("Graph.mapNode: expecting a callback.");
      const n = this._nodes.values();
      let r, i;
      const o = new Array(this.order);
      let s = 0;
      for (; r = n.next(), r.done !== true; ) i = r.value, o[s++] = t(i.key, i.attributes);
      return o;
    }
    someNode(t) {
      if (typeof t != "function") throw new X("Graph.someNode: expecting a callback.");
      const n = this._nodes.values();
      let r, i;
      for (; r = n.next(), r.done !== true; ) if (i = r.value, t(i.key, i.attributes)) return true;
      return false;
    }
    everyNode(t) {
      if (typeof t != "function") throw new X("Graph.everyNode: expecting a callback.");
      const n = this._nodes.values();
      let r, i;
      for (; r = n.next(), r.done !== true; ) if (i = r.value, !t(i.key, i.attributes)) return false;
      return true;
    }
    filterNodes(t) {
      if (typeof t != "function") throw new X("Graph.filterNodes: expecting a callback.");
      const n = this._nodes.values();
      let r, i;
      const o = [];
      for (; r = n.next(), r.done !== true; ) i = r.value, t(i.key, i.attributes) && o.push(i.key);
      return o;
    }
    reduceNodes(t, n) {
      if (typeof t != "function") throw new X("Graph.reduceNodes: expecting a callback.");
      if (arguments.length < 2) throw new X("Graph.reduceNodes: missing initial value. You must provide it because the callback takes more than one argument and we cannot infer the initial value from the first iteration, as you could with a simple array.");
      let r = n;
      const i = this._nodes.values();
      let o, s;
      for (; o = i.next(), o.done !== true; ) s = o.value, r = t(r, s.key, s.attributes);
      return r;
    }
    nodeEntries() {
      const t = this._nodes.values();
      return {
        [Symbol.iterator]() {
          return this;
        },
        next() {
          const n = t.next();
          if (n.done) return n;
          const r = n.value;
          return {
            value: {
              node: r.key,
              attributes: r.attributes
            },
            done: false
          };
        }
      };
    }
    export() {
      const t = new Array(this._nodes.size);
      let n = 0;
      this._nodes.forEach((i, o) => {
        t[n++] = w1(o, i);
      });
      const r = new Array(this._edges.size);
      return n = 0, this._edges.forEach((i, o) => {
        r[n++] = E1(this.type, o, i);
      }), {
        options: {
          type: this.type,
          multi: this.multi,
          allowSelfLoops: this.allowSelfLoops
        },
        attributes: this.getAttributes(),
        nodes: t,
        edges: r
      };
    }
    import(t, n = false) {
      if (t instanceof Pe) return t.forEachNode((l, c) => {
        n ? this.mergeNode(l, c) : this.addNode(l, c);
      }), t.forEachEdge((l, c, h, f, p, y, k) => {
        n ? k ? this.mergeUndirectedEdgeWithKey(l, h, f, c) : this.mergeDirectedEdgeWithKey(l, h, f, c) : k ? this.addUndirectedEdgeWithKey(l, h, f, c) : this.addDirectedEdgeWithKey(l, h, f, c);
      }), this;
      if (!ht(t)) throw new X("Graph.import: invalid argument. Expecting a serialized graph or, alternatively, a Graph instance.");
      if (t.attributes) {
        if (!ht(t.attributes)) throw new X("Graph.import: invalid attributes. Expecting a plain object.");
        n ? this.mergeAttributes(t.attributes) : this.replaceAttributes(t.attributes);
      }
      let r, i, o, s, a;
      if (t.nodes) {
        if (o = t.nodes, !Array.isArray(o)) throw new X("Graph.import: invalid nodes. Expecting an array.");
        for (r = 0, i = o.length; r < i; r++) {
          s = o[r], S1(s);
          const { key: l, attributes: c } = s;
          n ? this.mergeNode(l, c) : this.addNode(l, c);
        }
      }
      if (t.edges) {
        let l = false;
        if (this.type === "undirected" && (l = true), o = t.edges, !Array.isArray(o)) throw new X("Graph.import: invalid edges. Expecting an array.");
        for (r = 0, i = o.length; r < i; r++) {
          a = o[r], _1(a);
          const { source: c, target: h, attributes: f, undirected: p = l } = a;
          let y;
          "key" in a ? (y = n ? p ? this.mergeUndirectedEdgeWithKey : this.mergeDirectedEdgeWithKey : p ? this.addUndirectedEdgeWithKey : this.addDirectedEdgeWithKey, y.call(this, a.key, c, h, f)) : (y = n ? p ? this.mergeUndirectedEdge : this.mergeDirectedEdge : p ? this.addUndirectedEdge : this.addDirectedEdge, y.call(this, c, h, f));
        }
      }
      return this;
    }
    nullCopy(t) {
      const n = new Pe(it({}, this._options, t));
      return n.replaceAttributes(it({}, this.getAttributes())), n;
    }
    emptyCopy(t) {
      const n = this.nullCopy(t);
      return this._nodes.forEach((r, i) => {
        const o = it({}, r.attributes);
        r = new n.NodeDataClass(i, o), n._nodes.set(i, r);
      }), n;
    }
    copy(t) {
      if (t = t || {}, typeof t.type == "string" && t.type !== this.type && t.type !== "mixed") throw new ce(`Graph.copy: cannot create an incompatible copy from "${this.type}" type to "${t.type}" because this would mean losing information about the current graph.`);
      if (typeof t.multi == "boolean" && t.multi !== this.multi && t.multi !== true) throw new ce("Graph.copy: cannot create an incompatible copy by downgrading a multi graph to a simple one because this would mean losing information about the current graph.");
      if (typeof t.allowSelfLoops == "boolean" && t.allowSelfLoops !== this.allowSelfLoops && t.allowSelfLoops !== true) throw new ce("Graph.copy: cannot create an incompatible copy from a graph allowing self loops to one that does not because this would mean losing information about the current graph.");
      const n = this.emptyCopy(t), r = this._edges.values();
      let i, o;
      for (; i = r.next(), i.done !== true; ) o = i.value, Pg(n, "copy", false, o.undirected, o.key, o.source.key, o.target.key, it({}, o.attributes));
      return n;
    }
    toJSON() {
      return this.export();
    }
    toString() {
      return "[object Graph]";
    }
    inspect() {
      const t = {};
      this._nodes.forEach((o, s) => {
        t[s] = o.attributes;
      });
      const n = {}, r = {};
      this._edges.forEach((o, s) => {
        const a = o.undirected ? "--" : "->";
        let l = "", c = o.source.key, h = o.target.key, f;
        o.undirected && c > h && (f = c, c = h, h = f);
        const p = `(${c})${a}(${h})`;
        s.startsWith("geid_") ? this.multi && (typeof r[p] > "u" ? r[p] = 0 : r[p]++, l += `${r[p]}. `) : l += `[${s}]: `, l += p, n[l] = o.attributes;
      });
      const i = {};
      for (const o in this) this.hasOwnProperty(o) && !gf.has(o) && typeof this[o] != "function" && typeof o != "symbol" && (i[o] = this[o]);
      return i.attributes = this._attributes, i.nodes = t, i.edges = n, Qt(i, "constructor", this.constructor), i;
    }
  }
  typeof Symbol < "u" && (Pe.prototype[Symbol.for("nodejs.util.inspect.custom")] = Pe.prototype.inspect);
  x1.forEach((e) => {
    [
      "add",
      "merge",
      "update"
    ].forEach((t) => {
      const n = e.name(t), r = t === "add" ? Pg : R1;
      e.generateKey ? Pe.prototype[n] = function(i, o, s) {
        return r(this, n, true, (e.type || this.type) === "undirected", null, i, o, s, t === "update");
      } : Pe.prototype[n] = function(i, o, s, a) {
        return r(this, n, false, (e.type || this.type) === "undirected", i, o, s, a, t === "update");
      };
    });
  });
  OE(Pe);
  YE(Pe);
  c1(Pe);
  y1(Pe);
  class Ng extends Pe {
    constructor(t) {
      const n = it({
        type: "directed"
      }, t);
      if ("multi" in n && n.multi !== false) throw new X("DirectedGraph.from: inconsistent indication that the graph should be multi in given options!");
      if (n.type !== "directed") throw new X('DirectedGraph.from: inconsistent "' + n.type + '" type in given options!');
      super(n);
    }
  }
  class Fg extends Pe {
    constructor(t) {
      const n = it({
        type: "undirected"
      }, t);
      if ("multi" in n && n.multi !== false) throw new X("UndirectedGraph.from: inconsistent indication that the graph should be multi in given options!");
      if (n.type !== "undirected") throw new X('UndirectedGraph.from: inconsistent "' + n.type + '" type in given options!');
      super(n);
    }
  }
  class zg extends Pe {
    constructor(t) {
      const n = it({
        multi: true
      }, t);
      if ("multi" in n && n.multi !== true) throw new X("MultiGraph.from: inconsistent indication that the graph should be simple in given options!");
      super(n);
    }
  }
  class Og extends Pe {
    constructor(t) {
      const n = it({
        type: "directed",
        multi: true
      }, t);
      if ("multi" in n && n.multi !== true) throw new X("MultiDirectedGraph.from: inconsistent indication that the graph should be simple in given options!");
      if (n.type !== "directed") throw new X('MultiDirectedGraph.from: inconsistent "' + n.type + '" type in given options!');
      super(n);
    }
  }
  class Gg extends Pe {
    constructor(t) {
      const n = it({
        type: "undirected",
        multi: true
      }, t);
      if ("multi" in n && n.multi !== true) throw new X("MultiUndirectedGraph.from: inconsistent indication that the graph should be simple in given options!");
      if (n.type !== "undirected") throw new X('MultiUndirectedGraph.from: inconsistent "' + n.type + '" type in given options!');
      super(n);
    }
  }
  function xi(e) {
    e.from = function(t, n) {
      const r = it({}, t.options, n), i = new e(r);
      return i.import(t), i;
    };
  }
  xi(Pe);
  xi(Ng);
  xi(Fg);
  xi(zg);
  xi(Og);
  xi(Gg);
  Pe.Graph = Pe;
  Pe.DirectedGraph = Ng;
  Pe.UndirectedGraph = Fg;
  Pe.MultiGraph = zg;
  Pe.MultiDirectedGraph = Og;
  Pe.MultiUndirectedGraph = Gg;
  Pe.InvalidArgumentsGraphError = X;
  Pe.NotFoundGraphError = Y;
  Pe.UsageGraphError = ce;
  var A1 = function() {
    var t, n, r = {};
    (function() {
      var o = 0, s = 1, a = 2, l = 3, c = 4, h = 5, f = 6, p = 7, y = 8, k = 9, b = 0, I = 1, _ = 2, m = 0, v = 1, E = 2, A = 3, F = 4, R = 5, L = 6, C = 7, N = 8, V = 3, B = 10, K = 3, O = 9, re = 10;
      r.exports = function(J, S, j) {
        var H, D, x, Q, ie, _e, Se, oe, Z, Qe, ze = S.length, _n = j.length, st = J.adjustSizes, mt = J.barnesHutTheta * J.barnesHutTheta, Xe, me, ve, he, vt, le, se, U = [];
        for (x = 0; x < ze; x += B) S[x + c] = S[x + a], S[x + h] = S[x + l], S[x + a] = 0, S[x + l] = 0;
        if (J.outboundAttractionDistribution) {
          for (Xe = 0, x = 0; x < ze; x += B) Xe += S[x + f];
          Xe /= ze / B;
        }
        if (J.barnesHutOptimize) {
          var He = 1 / 0, Pt = -1 / 0, ln = 1 / 0, at = -1 / 0, yt, g, u;
          for (x = 0; x < ze; x += B) He = Math.min(He, S[x + o]), Pt = Math.max(Pt, S[x + o]), ln = Math.min(ln, S[x + s]), at = Math.max(at, S[x + s]);
          var d = Pt - He, w = at - ln;
          for (d > w ? (ln -= (d - w) / 2, at = ln + d) : (He -= (w - d) / 2, Pt = He + w), U[0 + m] = -1, U[0 + v] = (He + Pt) / 2, U[0 + E] = (ln + at) / 2, U[0 + A] = Math.max(Pt - He, at - ln), U[0 + F] = -1, U[0 + R] = -1, U[0 + L] = 0, U[0 + C] = 0, U[0 + N] = 0, H = 1, x = 0; x < ze; x += B) for (D = 0, u = V; ; ) if (U[D + R] >= 0) {
            S[x + o] < U[D + v] ? S[x + s] < U[D + E] ? yt = U[D + R] : yt = U[D + R] + O : S[x + s] < U[D + E] ? yt = U[D + R] + O * 2 : yt = U[D + R] + O * 3, U[D + C] = (U[D + C] * U[D + L] + S[x + o] * S[x + f]) / (U[D + L] + S[x + f]), U[D + N] = (U[D + N] * U[D + L] + S[x + s] * S[x + f]) / (U[D + L] + S[x + f]), U[D + L] += S[x + f], D = yt;
            continue;
          } else if (U[D + m] < 0) {
            U[D + m] = x;
            break;
          } else {
            if (U[D + R] = H * O, oe = U[D + A] / 2, Z = U[D + R], U[Z + m] = -1, U[Z + v] = U[D + v] - oe, U[Z + E] = U[D + E] - oe, U[Z + A] = oe, U[Z + F] = Z + O, U[Z + R] = -1, U[Z + L] = 0, U[Z + C] = 0, U[Z + N] = 0, Z += O, U[Z + m] = -1, U[Z + v] = U[D + v] - oe, U[Z + E] = U[D + E] + oe, U[Z + A] = oe, U[Z + F] = Z + O, U[Z + R] = -1, U[Z + L] = 0, U[Z + C] = 0, U[Z + N] = 0, Z += O, U[Z + m] = -1, U[Z + v] = U[D + v] + oe, U[Z + E] = U[D + E] - oe, U[Z + A] = oe, U[Z + F] = Z + O, U[Z + R] = -1, U[Z + L] = 0, U[Z + C] = 0, U[Z + N] = 0, Z += O, U[Z + m] = -1, U[Z + v] = U[D + v] + oe, U[Z + E] = U[D + E] + oe, U[Z + A] = oe, U[Z + F] = U[D + F], U[Z + R] = -1, U[Z + L] = 0, U[Z + C] = 0, U[Z + N] = 0, H += 4, S[U[D + m] + o] < U[D + v] ? S[U[D + m] + s] < U[D + E] ? yt = U[D + R] : yt = U[D + R] + O : S[U[D + m] + s] < U[D + E] ? yt = U[D + R] + O * 2 : yt = U[D + R] + O * 3, U[D + L] = S[U[D + m] + f], U[D + C] = S[U[D + m] + o], U[D + N] = S[U[D + m] + s], U[yt + m] = U[D + m], U[D + m] = -1, S[x + o] < U[D + v] ? S[x + s] < U[D + E] ? g = U[D + R] : g = U[D + R] + O : S[x + s] < U[D + E] ? g = U[D + R] + O * 2 : g = U[D + R] + O * 3, yt === g) if (u--) {
              D = yt;
              continue;
            } else {
              u = V;
              break;
            }
            U[g + m] = x;
            break;
          }
        }
        if (J.barnesHutOptimize) for (me = J.scalingRatio, x = 0; x < ze; x += B) for (D = 0; ; ) if (U[D + R] >= 0) if (le = Math.pow(S[x + o] - U[D + C], 2) + Math.pow(S[x + s] - U[D + N], 2), Qe = U[D + A], 4 * Qe * Qe / le < mt) {
          if (ve = S[x + o] - U[D + C], he = S[x + s] - U[D + N], st === true ? le > 0 ? (se = me * S[x + f] * U[D + L] / le, S[x + a] += ve * se, S[x + l] += he * se) : le < 0 && (se = -me * S[x + f] * U[D + L] / Math.sqrt(le), S[x + a] += ve * se, S[x + l] += he * se) : le > 0 && (se = me * S[x + f] * U[D + L] / le, S[x + a] += ve * se, S[x + l] += he * se), D = U[D + F], D < 0) break;
          continue;
        } else {
          D = U[D + R];
          continue;
        }
        else {
          if (_e = U[D + m], _e >= 0 && _e !== x && (ve = S[x + o] - S[_e + o], he = S[x + s] - S[_e + s], le = ve * ve + he * he, st === true ? le > 0 ? (se = me * S[x + f] * S[_e + f] / le, S[x + a] += ve * se, S[x + l] += he * se) : le < 0 && (se = -me * S[x + f] * S[_e + f] / Math.sqrt(le), S[x + a] += ve * se, S[x + l] += he * se) : le > 0 && (se = me * S[x + f] * S[_e + f] / le, S[x + a] += ve * se, S[x + l] += he * se)), D = U[D + F], D < 0) break;
          continue;
        }
        else for (me = J.scalingRatio, Q = 0; Q < ze; Q += B) for (ie = 0; ie < Q; ie += B) ve = S[Q + o] - S[ie + o], he = S[Q + s] - S[ie + s], st === true ? (le = Math.sqrt(ve * ve + he * he) - S[Q + y] - S[ie + y], le > 0 ? (se = me * S[Q + f] * S[ie + f] / le / le, S[Q + a] += ve * se, S[Q + l] += he * se, S[ie + a] -= ve * se, S[ie + l] -= he * se) : le < 0 && (se = 100 * me * S[Q + f] * S[ie + f], S[Q + a] += ve * se, S[Q + l] += he * se, S[ie + a] -= ve * se, S[ie + l] -= he * se)) : (le = Math.sqrt(ve * ve + he * he), le > 0 && (se = me * S[Q + f] * S[ie + f] / le / le, S[Q + a] += ve * se, S[Q + l] += he * se, S[ie + a] -= ve * se, S[ie + l] -= he * se));
        for (Z = J.gravity / J.scalingRatio, me = J.scalingRatio, x = 0; x < ze; x += B) se = 0, ve = S[x + o], he = S[x + s], le = Math.sqrt(Math.pow(ve, 2) + Math.pow(he, 2)), J.strongGravityMode ? le > 0 && (se = me * S[x + f] * Z) : le > 0 && (se = me * S[x + f] * Z / le), S[x + a] -= ve * se, S[x + l] -= he * se;
        for (me = 1 * (J.outboundAttractionDistribution ? Xe : 1), Se = 0; Se < _n; Se += K) Q = j[Se + b], ie = j[Se + I], oe = j[Se + _], vt = Math.pow(oe, J.edgeWeightInfluence), ve = S[Q + o] - S[ie + o], he = S[Q + s] - S[ie + s], st === true ? (le = Math.sqrt(ve * ve + he * he) - S[Q + y] - S[ie + y], J.linLogMode ? J.outboundAttractionDistribution ? le > 0 && (se = -me * vt * Math.log(1 + le) / le / S[Q + f]) : le > 0 && (se = -me * vt * Math.log(1 + le) / le) : J.outboundAttractionDistribution ? le > 0 && (se = -me * vt / S[Q + f]) : le > 0 && (se = -me * vt)) : (le = Math.sqrt(Math.pow(ve, 2) + Math.pow(he, 2)), J.linLogMode ? J.outboundAttractionDistribution ? le > 0 && (se = -me * vt * Math.log(1 + le) / le / S[Q + f]) : le > 0 && (se = -me * vt * Math.log(1 + le) / le) : J.outboundAttractionDistribution ? (le = 1, se = -me * vt / S[Q + f]) : (le = 1, se = -me * vt)), le > 0 && (S[Q + a] += ve * se, S[Q + l] += he * se, S[ie + a] -= ve * se, S[ie + l] -= he * se);
        var T, P, G, fe, ke, Ce;
        if (st === true) for (x = 0; x < ze; x += B) S[x + k] !== 1 && (T = Math.sqrt(Math.pow(S[x + a], 2) + Math.pow(S[x + l], 2)), T > re && (S[x + a] = S[x + a] * re / T, S[x + l] = S[x + l] * re / T), P = S[x + f] * Math.sqrt((S[x + c] - S[x + a]) * (S[x + c] - S[x + a]) + (S[x + h] - S[x + l]) * (S[x + h] - S[x + l])), G = Math.sqrt((S[x + c] + S[x + a]) * (S[x + c] + S[x + a]) + (S[x + h] + S[x + l]) * (S[x + h] + S[x + l])) / 2, fe = 0.1 * Math.log(1 + G) / (1 + Math.sqrt(P)), ke = S[x + o] + S[x + a] * (fe / J.slowDown), S[x + o] = ke, Ce = S[x + s] + S[x + l] * (fe / J.slowDown), S[x + s] = Ce);
        else for (x = 0; x < ze; x += B) S[x + k] !== 1 && (P = S[x + f] * Math.sqrt((S[x + c] - S[x + a]) * (S[x + c] - S[x + a]) + (S[x + h] - S[x + l]) * (S[x + h] - S[x + l])), G = Math.sqrt((S[x + c] + S[x + a]) * (S[x + c] + S[x + a]) + (S[x + h] + S[x + l]) * (S[x + h] + S[x + l])) / 2, fe = S[x + p] * Math.log(1 + G) / (1 + Math.sqrt(P)), S[x + p] = Math.min(1, Math.sqrt(fe * (Math.pow(S[x + a], 2) + Math.pow(S[x + l], 2)) / (1 + Math.sqrt(P)))), ke = S[x + o] + S[x + a] * (fe / J.slowDown), S[x + o] = ke, Ce = S[x + s] + S[x + l] * (fe / J.slowDown), S[x + s] = Ce);
        return {};
      };
    })();
    var i = r.exports;
    self.addEventListener("message", function(o) {
      var s = o.data;
      t = new Float32Array(s.nodes), s.edges && (n = new Float32Array(s.edges)), i(s.settings, t, n), self.postMessage({
        nodes: t.buffer
      }, [
        t.buffer
      ]);
    });
  }, Po = {};
  function L1(e) {
    return typeof e != "number" || isNaN(e) ? 1 : e;
  }
  function I1(e, t) {
    var n = {}, r = function(s) {
      return typeof s > "u" ? t : s;
    };
    typeof t == "function" && (r = t);
    var i = function(s) {
      return r(s[e]);
    }, o = function() {
      return r(void 0);
    };
    return typeof e == "string" ? (n.fromAttributes = i, n.fromGraph = function(s, a) {
      return i(s.getNodeAttributes(a));
    }, n.fromEntry = function(s, a) {
      return i(a);
    }) : typeof e == "function" ? (n.fromAttributes = function() {
      throw new Error("graphology-utils/getters/createNodeValueGetter: irrelevant usage.");
    }, n.fromGraph = function(s, a) {
      return r(e(a, s.getNodeAttributes(a)));
    }, n.fromEntry = function(s, a) {
      return r(e(s, a));
    }) : (n.fromAttributes = o, n.fromGraph = o, n.fromEntry = o), n;
  }
  function Ug(e, t) {
    var n = {}, r = function(s) {
      return typeof s > "u" ? t : s;
    };
    typeof t == "function" && (r = t);
    var i = function(s) {
      return r(s[e]);
    }, o = function() {
      return r(void 0);
    };
    return typeof e == "string" ? (n.fromAttributes = i, n.fromGraph = function(s, a) {
      return i(s.getEdgeAttributes(a));
    }, n.fromEntry = function(s, a) {
      return i(a);
    }, n.fromPartialEntry = n.fromEntry, n.fromMinimalEntry = n.fromEntry) : typeof e == "function" ? (n.fromAttributes = function() {
      throw new Error("graphology-utils/getters/createEdgeValueGetter: irrelevant usage.");
    }, n.fromGraph = function(s, a) {
      var l = s.extremities(a);
      return r(e(a, s.getEdgeAttributes(a), l[0], l[1], s.getNodeAttributes(l[0]), s.getNodeAttributes(l[1]), s.isUndirected(a)));
    }, n.fromEntry = function(s, a, l, c, h, f, p) {
      return r(e(s, a, l, c, h, f, p));
    }, n.fromPartialEntry = function(s, a, l, c) {
      return r(e(s, a, l, c));
    }, n.fromMinimalEntry = function(s, a) {
      return r(e(s, a));
    }) : (n.fromAttributes = o, n.fromGraph = o, n.fromEntry = o, n.fromMinimalEntry = o), n;
  }
  Po.createNodeValueGetter = I1;
  Po.createEdgeValueGetter = Ug;
  Po.createEdgeWeightGetter = function(e) {
    return Ug(e, L1);
  };
  var Xn = {}, Co = 10, vf = 3;
  Xn.assign = function(e) {
    e = e || {};
    var t = Array.prototype.slice.call(arguments).slice(1), n, r, i;
    for (n = 0, i = t.length; n < i; n++) if (t[n]) for (r in t[n]) e[r] = t[n][r];
    return e;
  };
  Xn.validateSettings = function(e) {
    return "linLogMode" in e && typeof e.linLogMode != "boolean" ? {
      message: "the `linLogMode` setting should be a boolean."
    } : "outboundAttractionDistribution" in e && typeof e.outboundAttractionDistribution != "boolean" ? {
      message: "the `outboundAttractionDistribution` setting should be a boolean."
    } : "adjustSizes" in e && typeof e.adjustSizes != "boolean" ? {
      message: "the `adjustSizes` setting should be a boolean."
    } : "edgeWeightInfluence" in e && typeof e.edgeWeightInfluence != "number" ? {
      message: "the `edgeWeightInfluence` setting should be a number."
    } : "scalingRatio" in e && !(typeof e.scalingRatio == "number" && e.scalingRatio >= 0) ? {
      message: "the `scalingRatio` setting should be a number >= 0."
    } : "strongGravityMode" in e && typeof e.strongGravityMode != "boolean" ? {
      message: "the `strongGravityMode` setting should be a boolean."
    } : "gravity" in e && !(typeof e.gravity == "number" && e.gravity >= 0) ? {
      message: "the `gravity` setting should be a number >= 0."
    } : "slowDown" in e && !(typeof e.slowDown == "number" || e.slowDown >= 0) ? {
      message: "the `slowDown` setting should be a number >= 0."
    } : "barnesHutOptimize" in e && typeof e.barnesHutOptimize != "boolean" ? {
      message: "the `barnesHutOptimize` setting should be a boolean."
    } : "barnesHutTheta" in e && !(typeof e.barnesHutTheta == "number" && e.barnesHutTheta >= 0) ? {
      message: "the `barnesHutTheta` setting should be a number >= 0."
    } : null;
  };
  Xn.graphToByteArrays = function(e, t) {
    var n = e.order, r = e.size, i = {}, o, s = new Float32Array(n * Co), a = new Float32Array(r * vf);
    return o = 0, e.forEachNode(function(l, c) {
      i[l] = o, s[o] = c.x, s[o + 1] = c.y, s[o + 2] = 0, s[o + 3] = 0, s[o + 4] = 0, s[o + 5] = 0, s[o + 6] = 1, s[o + 7] = 1, s[o + 8] = c.size || 1, s[o + 9] = c.fixed ? 1 : 0, o += Co;
    }), o = 0, e.forEachEdge(function(l, c, h, f, p, y, k) {
      var b = i[h], I = i[f], _ = t(l, c, h, f, p, y, k);
      s[b + 6] += _, s[I + 6] += _, a[o] = b, a[o + 1] = I, a[o + 2] = _, o += vf;
    }), {
      nodes: s,
      edges: a
    };
  };
  Xn.assignLayoutChanges = function(e, t, n) {
    var r = 0;
    e.updateEachNodeAttributes(function(i, o) {
      return o.x = t[r], o.y = t[r + 1], r += Co, n ? n(i, o) : o;
    });
  };
  Xn.readGraphPositions = function(e, t) {
    var n = 0;
    e.forEachNode(function(r, i) {
      t[n] = i.x, t[n + 1] = i.y, n += Co;
    });
  };
  Xn.collectLayoutChanges = function(e, t, n) {
    for (var r = e.nodes(), i = {}, o = 0, s = 0, a = t.length; o < a; o += Co) {
      if (n) {
        var l = Object.assign({}, e.getNodeAttributes(r[s]));
        l.x = t[o], l.y = t[o + 1], l = n(r[s], l), i[r[s]] = {
          x: l.x,
          y: l.y
        };
      } else i[r[s]] = {
        x: t[o],
        y: t[o + 1]
      };
      s++;
    }
    return i;
  };
  Xn.createWorker = function(t) {
    var n = window.URL || window.webkitURL, r = t.toString(), i = n.createObjectURL(new Blob([
      "(" + r + ").call(this);"
    ], {
      type: "text/javascript"
    })), o = new Worker(i);
    return n.revokeObjectURL(i), o;
  };
  var Bg = {
    linLogMode: false,
    outboundAttractionDistribution: false,
    adjustSizes: false,
    edgeWeightInfluence: 1,
    scalingRatio: 1,
    strongGravityMode: false,
    gravity: 1,
    slowDown: 1,
    barnesHutOptimize: false,
    barnesHutTheta: 0.5
  }, D1 = A1, P1 = _a, N1 = Po.createEdgeWeightGetter, yi = Xn, F1 = Bg;
  function Sr(e, t) {
    if (t = t || {}, !P1(e)) throw new Error("graphology-layout-forceatlas2/worker: the given graph is not a valid graphology instance.");
    var n = N1("getEdgeWeight" in t ? t.getEdgeWeight : "weight").fromEntry, r = yi.assign({}, F1, t.settings), i = yi.validateSettings(r);
    if (i) throw new Error("graphology-layout-forceatlas2/worker: " + i.message);
    this.worker = null, this.graph = e, this.settings = r, this.getEdgeWeight = n, this.matrices = null, this.running = false, this.killed = false, this.outputReducer = typeof t.outputReducer == "function" ? t.outputReducer : null, this.handleMessage = this.handleMessage.bind(this);
    var o = void 0, s = this;
    this.handleGraphUpdate = function() {
      s.worker && s.worker.terminate(), o && clearTimeout(o), o = setTimeout(function() {
        o = void 0, s.spawnWorker();
      }, 0);
    }, e.on("nodeAdded", this.handleGraphUpdate), e.on("edgeAdded", this.handleGraphUpdate), e.on("nodeDropped", this.handleGraphUpdate), e.on("edgeDropped", this.handleGraphUpdate), this.spawnWorker();
  }
  Sr.prototype.isRunning = function() {
    return this.running;
  };
  Sr.prototype.spawnWorker = function() {
    this.worker && this.worker.terminate(), this.worker = yi.createWorker(D1), this.worker.addEventListener("message", this.handleMessage), this.running && (this.running = false, this.start());
  };
  Sr.prototype.handleMessage = function(e) {
    if (this.running) {
      var t = new Float32Array(e.data.nodes);
      yi.assignLayoutChanges(this.graph, t, this.outputReducer), this.outputReducer && yi.readGraphPositions(this.graph, t), this.matrices.nodes = t, this.askForIterations();
    }
  };
  Sr.prototype.askForIterations = function(e) {
    var t = this.matrices, n = {
      settings: this.settings,
      nodes: t.nodes.buffer
    }, r = [
      t.nodes.buffer
    ];
    return e && (n.edges = t.edges.buffer, r.push(t.edges.buffer)), this.worker.postMessage(n, r), this;
  };
  Sr.prototype.start = function() {
    if (this.killed) throw new Error("graphology-layout-forceatlas2/worker.start: layout was killed.");
    return this.running ? this : (this.matrices = yi.graphToByteArrays(this.graph, this.getEdgeWeight), this.running = true, this.askForIterations(true), this);
  };
  Sr.prototype.stop = function() {
    return this.running = false, this;
  };
  Sr.prototype.kill = function() {
    if (this.killed) return this;
    this.running = false, this.killed = true, this.matrices = null, this.worker.terminate(), this.graph.removeListener("nodeAdded", this.handleGraphUpdate), this.graph.removeListener("edgeAdded", this.handleGraphUpdate), this.graph.removeListener("nodeDropped", this.handleGraphUpdate), this.graph.removeListener("edgeDropped", this.handleGraphUpdate);
  };
  var z1 = Sr;
  const O1 = To(z1);
  var qe = 0, Be = 1, Te = 2, Re = 3, Nn = 4, Fn = 5, Ae = 6, yf = 7, ss = 8, wf = 9, G1 = 0, U1 = 1, B1 = 2, ut = 0, Xt = 1, Rt = 2, kr = 3, er = 4, Ke = 5, zt = 6, bn = 7, xn = 8, Ef = 3, hn = 10, M1 = 3, kt = 9, dl = 10, $1 = function(t, n, r) {
    var i, o, s, a, l, c, h, f, p, y, k = n.length, b = r.length, I = t.adjustSizes, _ = t.barnesHutTheta * t.barnesHutTheta, m, v, E, A, F, R, L, C = [];
    for (s = 0; s < k; s += hn) n[s + Nn] = n[s + Te], n[s + Fn] = n[s + Re], n[s + Te] = 0, n[s + Re] = 0;
    if (t.outboundAttractionDistribution) {
      for (m = 0, s = 0; s < k; s += hn) m += n[s + Ae];
      m /= k / hn;
    }
    if (t.barnesHutOptimize) {
      var N = 1 / 0, V = -1 / 0, B = 1 / 0, K = -1 / 0, O, re, ae;
      for (s = 0; s < k; s += hn) N = Math.min(N, n[s + qe]), V = Math.max(V, n[s + qe]), B = Math.min(B, n[s + Be]), K = Math.max(K, n[s + Be]);
      var J = V - N, S = K - B;
      for (J > S ? (B -= (J - S) / 2, K = B + J) : (N -= (S - J) / 2, V = N + S), C[0 + ut] = -1, C[0 + Xt] = (N + V) / 2, C[0 + Rt] = (B + K) / 2, C[0 + kr] = Math.max(V - N, K - B), C[0 + er] = -1, C[0 + Ke] = -1, C[0 + zt] = 0, C[0 + bn] = 0, C[0 + xn] = 0, i = 1, s = 0; s < k; s += hn) for (o = 0, ae = Ef; ; ) if (C[o + Ke] >= 0) {
        n[s + qe] < C[o + Xt] ? n[s + Be] < C[o + Rt] ? O = C[o + Ke] : O = C[o + Ke] + kt : n[s + Be] < C[o + Rt] ? O = C[o + Ke] + kt * 2 : O = C[o + Ke] + kt * 3, C[o + bn] = (C[o + bn] * C[o + zt] + n[s + qe] * n[s + Ae]) / (C[o + zt] + n[s + Ae]), C[o + xn] = (C[o + xn] * C[o + zt] + n[s + Be] * n[s + Ae]) / (C[o + zt] + n[s + Ae]), C[o + zt] += n[s + Ae], o = O;
        continue;
      } else if (C[o + ut] < 0) {
        C[o + ut] = s;
        break;
      } else {
        if (C[o + Ke] = i * kt, f = C[o + kr] / 2, p = C[o + Ke], C[p + ut] = -1, C[p + Xt] = C[o + Xt] - f, C[p + Rt] = C[o + Rt] - f, C[p + kr] = f, C[p + er] = p + kt, C[p + Ke] = -1, C[p + zt] = 0, C[p + bn] = 0, C[p + xn] = 0, p += kt, C[p + ut] = -1, C[p + Xt] = C[o + Xt] - f, C[p + Rt] = C[o + Rt] + f, C[p + kr] = f, C[p + er] = p + kt, C[p + Ke] = -1, C[p + zt] = 0, C[p + bn] = 0, C[p + xn] = 0, p += kt, C[p + ut] = -1, C[p + Xt] = C[o + Xt] + f, C[p + Rt] = C[o + Rt] - f, C[p + kr] = f, C[p + er] = p + kt, C[p + Ke] = -1, C[p + zt] = 0, C[p + bn] = 0, C[p + xn] = 0, p += kt, C[p + ut] = -1, C[p + Xt] = C[o + Xt] + f, C[p + Rt] = C[o + Rt] + f, C[p + kr] = f, C[p + er] = C[o + er], C[p + Ke] = -1, C[p + zt] = 0, C[p + bn] = 0, C[p + xn] = 0, i += 4, n[C[o + ut] + qe] < C[o + Xt] ? n[C[o + ut] + Be] < C[o + Rt] ? O = C[o + Ke] : O = C[o + Ke] + kt : n[C[o + ut] + Be] < C[o + Rt] ? O = C[o + Ke] + kt * 2 : O = C[o + Ke] + kt * 3, C[o + zt] = n[C[o + ut] + Ae], C[o + bn] = n[C[o + ut] + qe], C[o + xn] = n[C[o + ut] + Be], C[O + ut] = C[o + ut], C[o + ut] = -1, n[s + qe] < C[o + Xt] ? n[s + Be] < C[o + Rt] ? re = C[o + Ke] : re = C[o + Ke] + kt : n[s + Be] < C[o + Rt] ? re = C[o + Ke] + kt * 2 : re = C[o + Ke] + kt * 3, O === re) if (ae--) {
          o = O;
          continue;
        } else {
          ae = Ef;
          break;
        }
        C[re + ut] = s;
        break;
      }
    }
    if (t.barnesHutOptimize) for (v = t.scalingRatio, s = 0; s < k; s += hn) for (o = 0; ; ) if (C[o + Ke] >= 0) if (R = Math.pow(n[s + qe] - C[o + bn], 2) + Math.pow(n[s + Be] - C[o + xn], 2), y = C[o + kr], 4 * y * y / R < _) {
      if (E = n[s + qe] - C[o + bn], A = n[s + Be] - C[o + xn], I === true ? R > 0 ? (L = v * n[s + Ae] * C[o + zt] / R, n[s + Te] += E * L, n[s + Re] += A * L) : R < 0 && (L = -v * n[s + Ae] * C[o + zt] / Math.sqrt(R), n[s + Te] += E * L, n[s + Re] += A * L) : R > 0 && (L = v * n[s + Ae] * C[o + zt] / R, n[s + Te] += E * L, n[s + Re] += A * L), o = C[o + er], o < 0) break;
      continue;
    } else {
      o = C[o + Ke];
      continue;
    }
    else {
      if (c = C[o + ut], c >= 0 && c !== s && (E = n[s + qe] - n[c + qe], A = n[s + Be] - n[c + Be], R = E * E + A * A, I === true ? R > 0 ? (L = v * n[s + Ae] * n[c + Ae] / R, n[s + Te] += E * L, n[s + Re] += A * L) : R < 0 && (L = -v * n[s + Ae] * n[c + Ae] / Math.sqrt(R), n[s + Te] += E * L, n[s + Re] += A * L) : R > 0 && (L = v * n[s + Ae] * n[c + Ae] / R, n[s + Te] += E * L, n[s + Re] += A * L)), o = C[o + er], o < 0) break;
      continue;
    }
    else for (v = t.scalingRatio, a = 0; a < k; a += hn) for (l = 0; l < a; l += hn) E = n[a + qe] - n[l + qe], A = n[a + Be] - n[l + Be], I === true ? (R = Math.sqrt(E * E + A * A) - n[a + ss] - n[l + ss], R > 0 ? (L = v * n[a + Ae] * n[l + Ae] / R / R, n[a + Te] += E * L, n[a + Re] += A * L, n[l + Te] -= E * L, n[l + Re] -= A * L) : R < 0 && (L = 100 * v * n[a + Ae] * n[l + Ae], n[a + Te] += E * L, n[a + Re] += A * L, n[l + Te] -= E * L, n[l + Re] -= A * L)) : (R = Math.sqrt(E * E + A * A), R > 0 && (L = v * n[a + Ae] * n[l + Ae] / R / R, n[a + Te] += E * L, n[a + Re] += A * L, n[l + Te] -= E * L, n[l + Re] -= A * L));
    for (p = t.gravity / t.scalingRatio, v = t.scalingRatio, s = 0; s < k; s += hn) L = 0, E = n[s + qe], A = n[s + Be], R = Math.sqrt(Math.pow(E, 2) + Math.pow(A, 2)), t.strongGravityMode ? R > 0 && (L = v * n[s + Ae] * p) : R > 0 && (L = v * n[s + Ae] * p / R), n[s + Te] -= E * L, n[s + Re] -= A * L;
    for (v = 1 * (t.outboundAttractionDistribution ? m : 1), h = 0; h < b; h += M1) a = r[h + G1], l = r[h + U1], f = r[h + B1], F = Math.pow(f, t.edgeWeightInfluence), E = n[a + qe] - n[l + qe], A = n[a + Be] - n[l + Be], I === true ? (R = Math.sqrt(E * E + A * A) - n[a + ss] - n[l + ss], t.linLogMode ? t.outboundAttractionDistribution ? R > 0 && (L = -v * F * Math.log(1 + R) / R / n[a + Ae]) : R > 0 && (L = -v * F * Math.log(1 + R) / R) : t.outboundAttractionDistribution ? R > 0 && (L = -v * F / n[a + Ae]) : R > 0 && (L = -v * F)) : (R = Math.sqrt(Math.pow(E, 2) + Math.pow(A, 2)), t.linLogMode ? t.outboundAttractionDistribution ? R > 0 && (L = -v * F * Math.log(1 + R) / R / n[a + Ae]) : R > 0 && (L = -v * F * Math.log(1 + R) / R) : t.outboundAttractionDistribution ? (R = 1, L = -v * F / n[a + Ae]) : (R = 1, L = -v * F)), R > 0 && (n[a + Te] += E * L, n[a + Re] += A * L, n[l + Te] -= E * L, n[l + Re] -= A * L);
    var j, H, D, x, Q, ie;
    if (I === true) for (s = 0; s < k; s += hn) n[s + wf] !== 1 && (j = Math.sqrt(Math.pow(n[s + Te], 2) + Math.pow(n[s + Re], 2)), j > dl && (n[s + Te] = n[s + Te] * dl / j, n[s + Re] = n[s + Re] * dl / j), H = n[s + Ae] * Math.sqrt((n[s + Nn] - n[s + Te]) * (n[s + Nn] - n[s + Te]) + (n[s + Fn] - n[s + Re]) * (n[s + Fn] - n[s + Re])), D = Math.sqrt((n[s + Nn] + n[s + Te]) * (n[s + Nn] + n[s + Te]) + (n[s + Fn] + n[s + Re]) * (n[s + Fn] + n[s + Re])) / 2, x = 0.1 * Math.log(1 + D) / (1 + Math.sqrt(H)), Q = n[s + qe] + n[s + Te] * (x / t.slowDown), n[s + qe] = Q, ie = n[s + Be] + n[s + Re] * (x / t.slowDown), n[s + Be] = ie);
    else for (s = 0; s < k; s += hn) n[s + wf] !== 1 && (H = n[s + Ae] * Math.sqrt((n[s + Nn] - n[s + Te]) * (n[s + Nn] - n[s + Te]) + (n[s + Fn] - n[s + Re]) * (n[s + Fn] - n[s + Re])), D = Math.sqrt((n[s + Nn] + n[s + Te]) * (n[s + Nn] + n[s + Te]) + (n[s + Fn] + n[s + Re]) * (n[s + Fn] + n[s + Re])) / 2, x = n[s + yf] * Math.log(1 + D) / (1 + Math.sqrt(H)), n[s + yf] = Math.min(1, Math.sqrt(x * (Math.pow(n[s + Te], 2) + Math.pow(n[s + Re], 2)) / (1 + Math.sqrt(H)))), Q = n[s + qe] + n[s + Te] * (x / t.slowDown), n[s + qe] = Q, ie = n[s + Be] + n[s + Re] * (x / t.slowDown), n[s + Be] = ie);
    return {};
  }, j1 = _a, H1 = Po.createEdgeWeightGetter, W1 = $1, ji = Xn, V1 = Bg;
  function Mg(e, t, n) {
    if (!j1(t)) throw new Error("graphology-layout-forceatlas2: the given graph is not a valid graphology instance.");
    typeof n == "number" && (n = {
      iterations: n
    });
    var r = n.iterations;
    if (typeof r != "number") throw new Error("graphology-layout-forceatlas2: invalid number of iterations.");
    if (r <= 0) throw new Error("graphology-layout-forceatlas2: you should provide a positive number of iterations.");
    var i = H1("getEdgeWeight" in n ? n.getEdgeWeight : "weight").fromEntry, o = typeof n.outputReducer == "function" ? n.outputReducer : null, s = ji.assign({}, V1, n.settings), a = ji.validateSettings(s);
    if (a) throw new Error("graphology-layout-forceatlas2: " + a.message);
    var l = ji.graphToByteArrays(t, i), c;
    for (c = 0; c < r; c++) W1(s, l.nodes, l.edges);
    if (e) {
      ji.assignLayoutChanges(t, l.nodes, o);
      return;
    }
    return ji.collectLayoutChanges(t, l.nodes);
  }
  function K1(e) {
    var t = typeof e == "number" ? e : e.order;
    return {
      barnesHutOptimize: t > 2e3,
      strongGravityMode: true,
      gravity: 0.05,
      scalingRatio: 10,
      slowDown: 1 + Math.log(t)
    };
  }
  var Ec = Mg.bind(null, false);
  Ec.assign = Mg.bind(null, true);
  Ec.inferSettings = K1;
  var Y1 = Ec;
  const Q1 = To(Y1);
  var Hi = 0, Wi = 1, as = 2, Vi = 3;
  function X1(e, t) {
    return e + "\xA7" + t;
  }
  function Sf() {
    return 0.01 * (0.5 - Math.random());
  }
  var Z1 = function(t, n) {
    var r = t.margin, i = t.ratio, o = t.expansion, s = t.gridSize, a = t.speed, l, c, h, f, p, y, k = true, b = n.length, I = b / Vi | 0, _ = new Float32Array(I), m = new Float32Array(I), v = 1 / 0, E = 1 / 0, A = -1 / 0, F = -1 / 0;
    for (l = 0; l < b; l += Vi) h = n[l + Hi], f = n[l + Wi], y = n[l + as] * i + r, v = Math.min(v, h - y), A = Math.max(A, h + y), E = Math.min(E, f - y), F = Math.max(F, f + y);
    var R = A - v, L = F - E, C = (v + A) / 2, N = (E + F) / 2;
    v = C - o * R / 2, A = C + o * R / 2, E = N - o * L / 2, F = N + o * L / 2;
    var V = new Array(s * s), B = V.length, K;
    for (K = 0; K < B; K++) V[K] = [];
    var O, re, ae, J, S, j, H, D, x, Q;
    for (l = 0; l < b; l += Vi) for (h = n[l + Hi], f = n[l + Wi], y = n[l + as] * i + r, O = h - y, re = h + y, ae = f - y, J = f + y, S = Math.floor(s * (O - v) / (A - v)), j = Math.floor(s * (re - v) / (A - v)), H = Math.floor(s * (ae - E) / (F - E)), D = Math.floor(s * (J - E) / (F - E)), x = S; x <= j; x++) for (Q = H; Q <= D; Q++) V[x * s + Q].push(l);
    var ie, _e = /* @__PURE__ */ new Set(), Se, oe, Z, Qe, ze, _n, st, mt, Xe, me, ve, he, vt;
    for (K = 0; K < B; K++) for (ie = V[K], l = 0, p = ie.length; l < p; l++) for (Se = ie[l], Z = n[Se + Hi], ze = n[Se + Wi], st = n[Se + as], c = l + 1; c < p; c++) oe = ie[c], Xe = X1(Se, oe), !(B > 1 && _e.has(Xe)) && (B > 1 && _e.add(Xe), Qe = n[oe + Hi], _n = n[oe + Wi], mt = n[oe + as], me = Qe - Z, ve = _n - ze, he = Math.sqrt(me * me + ve * ve), vt = he < st * i + r + (mt * i + r), vt && (k = false, oe = oe / Vi | 0, he > 0 ? (_[oe] += me / he * (1 + st), m[oe] += ve / he * (1 + st)) : (_[oe] += R * Sf(), m[oe] += L * Sf())));
    for (l = 0, c = 0; l < b; l += Vi, c++) n[l + Hi] += _[c] * 0.1 * a, n[l + Wi] += m[c] * 0.1 * a;
    return {
      converged: k
    };
  }, Ci = {}, qs = 3;
  Ci.validateSettings = function(e) {
    return "gridSize" in e && typeof e.gridSize != "number" || e.gridSize <= 0 ? {
      message: "the `gridSize` setting should be a positive number."
    } : "margin" in e && typeof e.margin != "number" || e.margin < 0 ? {
      message: "the `margin` setting should be 0 or a positive number."
    } : "expansion" in e && typeof e.expansion != "number" || e.expansion <= 0 ? {
      message: "the `expansion` setting should be a positive number."
    } : "ratio" in e && typeof e.ratio != "number" || e.ratio <= 0 ? {
      message: "the `ratio` setting should be a positive number."
    } : "speed" in e && typeof e.speed != "number" || e.speed <= 0 ? {
      message: "the `speed` setting should be a positive number."
    } : null;
  };
  Ci.graphToByteArray = function(e, t) {
    var n = e.order, r = new Float32Array(n * qs), i = 0;
    return e.forEachNode(function(o, s) {
      typeof t == "function" && (s = t(o, s)), r[i] = s.x, r[i + 1] = s.y, r[i + 2] = s.size || 1, i += qs;
    }), r;
  };
  Ci.assignLayoutChanges = function(e, t, n) {
    var r = 0;
    e.forEachNode(function(i) {
      var o = {
        x: t[r],
        y: t[r + 1]
      };
      typeof n == "function" && (o = n(i, o)), e.mergeNodeAttributes(i, o), r += qs;
    });
  };
  Ci.collectLayoutChanges = function(e, t, n) {
    var r = {}, i = 0;
    return e.forEachNode(function(o) {
      var s = {
        x: t[i],
        y: t[i + 1]
      };
      typeof n == "function" && (s = n(o, s)), r[o] = s, i += qs;
    }), r;
  };
  Ci.createWorker = function(t) {
    var n = window.URL || window.webkitURL, r = t.toString(), i = n.createObjectURL(new Blob([
      "(" + r + ").call(this);"
    ], {
      type: "text/javascript"
    })), o = new Worker(i);
    return n.revokeObjectURL(i), o;
  };
  var q1 = {
    gridSize: 20,
    margin: 5,
    expansion: 1.1,
    ratio: 1,
    speed: 3
  }, J1 = _a, eS = Z1, ls = Ci, tS = q1, nS = 500;
  function $g(e, t, n) {
    if (!J1(t)) throw new Error("graphology-layout-noverlap: the given graph is not a valid graphology instance.");
    typeof n == "number" ? n = {
      maxIterations: n
    } : n = n || {};
    var r = n.maxIterations || nS;
    if (typeof r != "number" || r <= 0) throw new Error("graphology-layout-force: you should provide a positive number of maximum iterations.");
    var i = Object.assign({}, tS, n.settings), o = ls.validateSettings(i);
    if (o) throw new Error("graphology-layout-noverlap: " + o.message);
    var s = ls.graphToByteArray(t, n.inputReducer), a = false, l;
    for (l = 0; l < r && !a; l++) a = eS(i, s).converged;
    if (e) {
      ls.assignLayoutChanges(t, s, n.outputReducer);
      return;
    }
    return ls.collectLayoutChanges(t, s, n.outputReducer);
  }
  var jg = $g.bind(null, false);
  jg.assign = $g.bind(null, true);
  var rS = jg;
  const iS = To(rS);
  function oS(e, t) {
    if (typeof e != "object" || !e) return e;
    var n = e[Symbol.toPrimitive];
    if (n !== void 0) {
      var r = n.call(e, t);
      if (typeof r != "object") return r;
      throw new TypeError("@@toPrimitive must return a primitive value.");
    }
    return (t === "string" ? String : Number)(e);
  }
  function Hg(e) {
    var t = oS(e, "string");
    return typeof t == "symbol" ? t : t + "";
  }
  function Wg(e, t, n) {
    return (t = Hg(t)) in e ? Object.defineProperty(e, t, {
      value: n,
      enumerable: true,
      configurable: true,
      writable: true
    }) : e[t] = n, e;
  }
  function _f(e, t) {
    var n = Object.keys(e);
    if (Object.getOwnPropertySymbols) {
      var r = Object.getOwnPropertySymbols(e);
      t && (r = r.filter(function(i) {
        return Object.getOwnPropertyDescriptor(e, i).enumerable;
      })), n.push.apply(n, r);
    }
    return n;
  }
  function Js(e) {
    for (var t = 1; t < arguments.length; t++) {
      var n = arguments[t] != null ? arguments[t] : {};
      t % 2 ? _f(Object(n), true).forEach(function(r) {
        Wg(e, r, n[r]);
      }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(n)) : _f(Object(n)).forEach(function(r) {
        Object.defineProperty(e, r, Object.getOwnPropertyDescriptor(n, r));
      });
    }
    return e;
  }
  function sS(e, t) {
    if (!(e instanceof t)) throw new TypeError("Cannot call a class as a function");
  }
  function aS(e, t) {
    for (var n = 0; n < t.length; n++) {
      var r = t[n];
      r.enumerable = r.enumerable || false, r.configurable = true, "value" in r && (r.writable = true), Object.defineProperty(e, Hg(r.key), r);
    }
  }
  function lS(e, t, n) {
    return t && aS(e.prototype, t), Object.defineProperty(e, "prototype", {
      writable: false
    }), e;
  }
  function ea(e) {
    return ea = Object.setPrototypeOf ? Object.getPrototypeOf.bind() : function(t) {
      return t.__proto__ || Object.getPrototypeOf(t);
    }, ea(e);
  }
  function Vg() {
    try {
      var e = !Boolean.prototype.valueOf.call(Reflect.construct(Boolean, [], function() {
      }));
    } catch {
    }
    return (Vg = function() {
      return !!e;
    })();
  }
  function Kg(e) {
    if (e === void 0) throw new ReferenceError("this hasn't been initialised - super() hasn't been called");
    return e;
  }
  function uS(e, t) {
    if (t && (typeof t == "object" || typeof t == "function")) return t;
    if (t !== void 0) throw new TypeError("Derived constructors may only return object or undefined");
    return Kg(e);
  }
  function cS(e, t, n) {
    return t = ea(t), uS(e, Vg() ? Reflect.construct(t, n || [], ea(e).constructor) : t.apply(e, n));
  }
  function pu(e, t) {
    return pu = Object.setPrototypeOf ? Object.setPrototypeOf.bind() : function(n, r) {
      return n.__proto__ = r, n;
    }, pu(e, t);
  }
  function dS(e, t) {
    if (typeof t != "function" && t !== null) throw new TypeError("Super expression must either be null or a function");
    e.prototype = Object.create(t && t.prototype, {
      constructor: {
        value: e,
        writable: true,
        configurable: true
      }
    }), Object.defineProperty(e, "prototype", {
      writable: false
    }), t && pu(e, t);
  }
  function gu(e, t) {
    (t == null || t > e.length) && (t = e.length);
    for (var n = 0, r = Array(t); n < t; n++) r[n] = e[n];
    return r;
  }
  function fS(e) {
    if (Array.isArray(e)) return gu(e);
  }
  function hS(e) {
    if (typeof Symbol < "u" && e[Symbol.iterator] != null || e["@@iterator"] != null) return Array.from(e);
  }
  function pS(e, t) {
    if (e) {
      if (typeof e == "string") return gu(e, t);
      var n = {}.toString.call(e).slice(8, -1);
      return n === "Object" && e.constructor && (n = e.constructor.name), n === "Map" || n === "Set" ? Array.from(e) : n === "Arguments" || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(n) ? gu(e, t) : void 0;
    }
  }
  function gS() {
    throw new TypeError(`Invalid attempt to spread non-iterable instance.
In order to be iterable, non-array objects must have a [Symbol.iterator]() method.`);
  }
  function fl(e) {
    return fS(e) || hS(e) || pS(e) || gS();
  }
  function Yg(e, t, n, r) {
    var i = Math.pow(1 - e, 2) * t.x + 2 * (1 - e) * e * n.x + Math.pow(e, 2) * r.x, o = Math.pow(1 - e, 2) * t.y + 2 * (1 - e) * e * n.y + Math.pow(e, 2) * r.y;
    return {
      x: i,
      y: o
    };
  }
  function mS(e, t, n) {
    for (var r = 20, i = 0, o = e, s = 0; s < r; s++) {
      var a = Yg((s + 1) / r, e, t, n);
      i += Math.sqrt(Math.pow(o.x - a.x, 2) + Math.pow(o.y - a.y, 2)), o = a;
    }
    return i;
  }
  function vS(e) {
    var t = e.curvatureAttribute, n = e.defaultCurvature, r = e.keepLabelUpright, i = r === void 0 ? true : r;
    return function(o, s, a, l, c) {
      var h = c.edgeLabelSize, f = s[t] || n, p = c.edgeLabelFont, y = c.edgeLabelWeight, k = c.edgeLabelColor.attribute ? s[c.edgeLabelColor.attribute] || c.edgeLabelColor.color || "#000" : c.edgeLabelColor.color, b = s.label;
      if (b) {
        o.fillStyle = k, o.font = "".concat(y, " ").concat(h, "px ").concat(p);
        var I = !i || a.x < l.x, _ = I ? a.x : l.x, m = I ? a.y : l.y, v = I ? l.x : a.x, E = I ? l.y : a.y, A = (_ + v) / 2, F = (m + E) / 2, R = v - _, L = E - m, C = Math.sqrt(Math.pow(R, 2) + Math.pow(L, 2)), N = I ? 1 : -1, V = A + L * f * N, B = F - R * f * N, K = s.size * 0.7 + 5, O = {
          x: B - m,
          y: -(V - _)
        }, re = Math.sqrt(Math.pow(O.x, 2) + Math.pow(O.y, 2)), ae = {
          x: E - B,
          y: -(v - V)
        }, J = Math.sqrt(Math.pow(ae.x, 2) + Math.pow(ae.y, 2));
        _ += K * O.x / re, m += K * O.y / re, v += K * ae.x / J, E += K * ae.y / J, V += K * L / C, B -= K * R / C;
        var S = {
          x: V,
          y: B
        }, j = {
          x: _,
          y: m
        }, H = {
          x: v,
          y: E
        }, D = mS(j, S, H);
        if (!(D < a.size + l.size)) {
          var x = o.measureText(b).width, Q = D - a.size - l.size;
          if (x > Q) {
            var ie = "\u2026";
            for (b = b + ie, x = o.measureText(b).width; x > Q && b.length > 1; ) b = b.slice(0, -2) + ie, x = o.measureText(b).width;
            if (b.length < 4) return;
          }
          for (var _e = {}, Se = 0, oe = b.length; Se < oe; Se++) {
            var Z = b[Se];
            _e[Z] || (_e[Z] = o.measureText(Z).width * (1 + f * 0.35));
          }
          for (var Qe = 0.5 - x / D / 2, ze = 0, _n = b.length; ze < _n; ze++) {
            var st = b[ze], mt = Yg(Qe, j, S, H), Xe = 2 * (1 - Qe) * (V - _) + 2 * Qe * (v - V), me = 2 * (1 - Qe) * (B - m) + 2 * Qe * (E - B), ve = Math.atan2(me, Xe);
            o.save(), o.translate(mt.x, mt.y), o.rotate(ve), o.fillText(st, 0, 0), o.restore(), Qe += _e[st] / D;
          }
        }
      }
    };
  }
  function yS(e) {
    var t = e.arrowHead, n = (t == null ? void 0 : t.extremity) === "target" || (t == null ? void 0 : t.extremity) === "both", r = (t == null ? void 0 : t.extremity) === "source" || (t == null ? void 0 : t.extremity) === "both", i = `
precision highp float;

varying vec4 v_color;
varying float v_thickness;
varying float v_feather;
varying vec2 v_cpA;
varying vec2 v_cpB;
varying vec2 v_cpC;
`.concat(n ? `
varying float v_targetSize;
varying vec2 v_targetPoint;` : "", `
`).concat(r ? `
varying float v_sourceSize;
varying vec2 v_sourcePoint;` : "", `
`).concat(t ? `
uniform float u_lengthToThicknessRatio;
uniform float u_widenessToThicknessRatio;` : "", `

float det(vec2 a, vec2 b) {
  return a.x * b.y - b.x * a.y;
}

vec2 getDistanceVector(vec2 b0, vec2 b1, vec2 b2) {
  float a = det(b0, b2), b = 2.0 * det(b1, b0), d = 2.0 * det(b2, b1);
  float f = b * d - a * a;
  vec2 d21 = b2 - b1, d10 = b1 - b0, d20 = b2 - b0;
  vec2 gf = 2.0 * (b * d21 + d * d10 + a * d20);
  gf = vec2(gf.y, -gf.x);
  vec2 pp = -f * gf / dot(gf, gf);
  vec2 d0p = b0 - pp;
  float ap = det(d0p, d20), bp = 2.0 * det(d10, d0p);
  float t = clamp((ap + bp) / (2.0 * a + b + d), 0.0, 1.0);
  return mix(mix(b0, b1, t), mix(b1, b2, t), t);
}

float distToQuadraticBezierCurve(vec2 p, vec2 b0, vec2 b1, vec2 b2) {
  return length(getDistanceVector(b0 - p, b1 - p, b2 - p));
}

const vec4 transparent = vec4(0.0, 0.0, 0.0, 0.0);

void main(void) {
  float dist = distToQuadraticBezierCurve(gl_FragCoord.xy, v_cpA, v_cpB, v_cpC);
  float thickness = v_thickness;
`).concat(n ? `
  float distToTarget = length(gl_FragCoord.xy - v_targetPoint);
  float targetArrowLength = v_targetSize + thickness * u_lengthToThicknessRatio;
  if (distToTarget < targetArrowLength) {
    thickness = (distToTarget - v_targetSize) / (targetArrowLength - v_targetSize) * u_widenessToThicknessRatio * thickness;
  }` : "", `
`).concat(r ? `
  float distToSource = length(gl_FragCoord.xy - v_sourcePoint);
  float sourceArrowLength = v_sourceSize + thickness * u_lengthToThicknessRatio;
  if (distToSource < sourceArrowLength) {
    thickness = (distToSource - v_sourceSize) / (sourceArrowLength - v_sourceSize) * u_widenessToThicknessRatio * thickness;
  }` : "", `

  float halfThickness = thickness / 2.0;
  if (dist < halfThickness) {
    #ifdef PICKING_MODE
    gl_FragColor = v_color;
    #else
    float t = smoothstep(
      halfThickness - v_feather,
      halfThickness,
      dist
    );

    gl_FragColor = mix(v_color, transparent, t);
    #endif
  } else {
    gl_FragColor = transparent;
  }
}
`);
    return i;
  }
  function wS(e) {
    var t = e.arrowHead, n = (t == null ? void 0 : t.extremity) === "target" || (t == null ? void 0 : t.extremity) === "both", r = (t == null ? void 0 : t.extremity) === "source" || (t == null ? void 0 : t.extremity) === "both", i = `
attribute vec4 a_id;
attribute vec4 a_color;
attribute float a_direction;
attribute float a_thickness;
attribute vec2 a_source;
attribute vec2 a_target;
attribute float a_current;
attribute float a_curvature;
`.concat(n ? `attribute float a_targetSize;
` : "", `
`).concat(r ? `attribute float a_sourceSize;
` : "", `

uniform mat3 u_matrix;
uniform float u_sizeRatio;
uniform float u_pixelRatio;
uniform vec2 u_dimensions;
uniform float u_minEdgeThickness;
uniform float u_feather;

varying vec4 v_color;
varying float v_thickness;
varying float v_feather;
varying vec2 v_cpA;
varying vec2 v_cpB;
varying vec2 v_cpC;
`).concat(n ? `
varying float v_targetSize;
varying vec2 v_targetPoint;` : "", `
`).concat(r ? `
varying float v_sourceSize;
varying vec2 v_sourcePoint;` : "", `
`).concat(t ? `
uniform float u_widenessToThicknessRatio;` : "", `

const float bias = 255.0 / 254.0;
const float epsilon = 0.7;

vec2 clipspaceToViewport(vec2 pos, vec2 dimensions) {
  return vec2(
    (pos.x + 1.0) * dimensions.x / 2.0,
    (pos.y + 1.0) * dimensions.y / 2.0
  );
}

vec2 viewportToClipspace(vec2 pos, vec2 dimensions) {
  return vec2(
    pos.x / dimensions.x * 2.0 - 1.0,
    pos.y / dimensions.y * 2.0 - 1.0
  );
}

void main() {
  float minThickness = u_minEdgeThickness;

  // Selecting the correct position
  // Branchless "position = a_source if a_current == 1.0 else a_target"
  vec2 position = a_source * max(0.0, a_current) + a_target * max(0.0, 1.0 - a_current);
  position = (u_matrix * vec3(position, 1)).xy;

  vec2 source = (u_matrix * vec3(a_source, 1)).xy;
  vec2 target = (u_matrix * vec3(a_target, 1)).xy;

  vec2 viewportPosition = clipspaceToViewport(position, u_dimensions);
  vec2 viewportSource = clipspaceToViewport(source, u_dimensions);
  vec2 viewportTarget = clipspaceToViewport(target, u_dimensions);

  vec2 delta = viewportTarget.xy - viewportSource.xy;
  float len = length(delta);
  vec2 normal = vec2(-delta.y, delta.x) * a_direction;
  vec2 unitNormal = normal / len;
  float boundingBoxThickness = len * a_curvature;

  float curveThickness = max(minThickness, a_thickness / u_sizeRatio);
  v_thickness = curveThickness * u_pixelRatio;
  v_feather = u_feather;

  v_cpA = viewportSource;
  v_cpB = 0.5 * (viewportSource + viewportTarget) + unitNormal * a_direction * boundingBoxThickness;
  v_cpC = viewportTarget;

  vec2 viewportOffsetPosition = (
    viewportPosition +
    unitNormal * (boundingBoxThickness / 2.0 + sign(boundingBoxThickness) * (`).concat(t ? "curveThickness * u_widenessToThicknessRatio" : "curveThickness", ` + epsilon)) *
    max(0.0, a_direction) // NOTE: cutting the bounding box in half to avoid overdraw
  );

  position = viewportToClipspace(viewportOffsetPosition, u_dimensions);
  gl_Position = vec4(position, 0, 1);
    
`).concat(n ? `
  v_targetSize = a_targetSize * u_pixelRatio / u_sizeRatio;
  v_targetPoint = viewportTarget;
` : "", `
`).concat(r ? `
  v_sourceSize = a_sourceSize * u_pixelRatio / u_sizeRatio;
  v_sourcePoint = viewportSource;
` : "", `

  #ifdef PICKING_MODE
  // For picking mode, we use the ID as the color:
  v_color = a_id;
  #else
  // For normal mode, we use the color:
  v_color = a_color;
  #endif

  v_color.a *= bias;
}
`);
    return i;
  }
  var Qg = 0.25, ES = {
    arrowHead: null,
    curvatureAttribute: "curvature",
    defaultCurvature: Qg
  }, Xg = WebGLRenderingContext, kf = Xg.UNSIGNED_BYTE, tr = Xg.FLOAT;
  function Sc(e) {
    var t = Js(Js({}, ES), e || {}), n = t, r = n.arrowHead, i = n.curvatureAttribute, o = n.drawLabel, s = (r == null ? void 0 : r.extremity) === "target" || (r == null ? void 0 : r.extremity) === "both", a = (r == null ? void 0 : r.extremity) === "source" || (r == null ? void 0 : r.extremity) === "both", l = [
      "u_matrix",
      "u_sizeRatio",
      "u_dimensions",
      "u_pixelRatio",
      "u_feather",
      "u_minEdgeThickness"
    ].concat(fl(r ? [
      "u_lengthToThicknessRatio",
      "u_widenessToThicknessRatio"
    ] : []));
    return function(c) {
      dS(h, c);
      function h() {
        var f;
        sS(this, h);
        for (var p = arguments.length, y = new Array(p), k = 0; k < p; k++) y[k] = arguments[k];
        return f = cS(this, h, [].concat(y)), Wg(Kg(f), "drawLabel", o || vS(t)), f;
      }
      return lS(h, [
        {
          key: "getDefinition",
          value: function() {
            return {
              VERTICES: 6,
              VERTEX_SHADER_SOURCE: wS(t),
              FRAGMENT_SHADER_SOURCE: yS(t),
              METHOD: WebGLRenderingContext.TRIANGLES,
              UNIFORMS: l,
              ATTRIBUTES: [
                {
                  name: "a_source",
                  size: 2,
                  type: tr
                },
                {
                  name: "a_target",
                  size: 2,
                  type: tr
                }
              ].concat(fl(s ? [
                {
                  name: "a_targetSize",
                  size: 1,
                  type: tr
                }
              ] : []), fl(a ? [
                {
                  name: "a_sourceSize",
                  size: 1,
                  type: tr
                }
              ] : []), [
                {
                  name: "a_thickness",
                  size: 1,
                  type: tr
                },
                {
                  name: "a_curvature",
                  size: 1,
                  type: tr
                },
                {
                  name: "a_color",
                  size: 4,
                  type: kf,
                  normalized: true
                },
                {
                  name: "a_id",
                  size: 4,
                  type: kf,
                  normalized: true
                }
              ]),
              CONSTANT_ATTRIBUTES: [
                {
                  name: "a_current",
                  size: 1,
                  type: tr
                },
                {
                  name: "a_direction",
                  size: 1,
                  type: tr
                }
              ],
              CONSTANT_DATA: [
                [
                  0,
                  1
                ],
                [
                  0,
                  -1
                ],
                [
                  1,
                  1
                ],
                [
                  0,
                  -1
                ],
                [
                  1,
                  1
                ],
                [
                  1,
                  -1
                ]
              ]
            };
          }
        },
        {
          key: "processVisibleItem",
          value: function(p, y, k, b, I) {
            var _, m = I.size || 1, v = k.x, E = k.y, A = b.x, F = b.y, R = _i(I.color), L = (_ = I[i]) !== null && _ !== void 0 ? _ : Qg, C = this.array;
            C[y++] = v, C[y++] = E, C[y++] = A, C[y++] = F, s && (C[y++] = b.size), a && (C[y++] = k.size), C[y++] = m, C[y++] = L, C[y++] = R, C[y++] = p;
          }
        },
        {
          key: "setUniforms",
          value: function(p, y) {
            var k = y.gl, b = y.uniformLocations, I = b.u_matrix, _ = b.u_pixelRatio, m = b.u_feather, v = b.u_sizeRatio, E = b.u_dimensions, A = b.u_minEdgeThickness;
            if (k.uniformMatrix3fv(I, false, p.matrix), k.uniform1f(_, p.pixelRatio), k.uniform1f(v, p.sizeRatio), k.uniform1f(m, p.antiAliasingFeather), k.uniform2f(E, p.width * p.pixelRatio, p.height * p.pixelRatio), k.uniform1f(A, p.minEdgeThickness), r) {
              var F = b.u_lengthToThicknessRatio, R = b.u_widenessToThicknessRatio;
              k.uniform1f(F, r.lengthToThicknessRatio), k.uniform1f(R, r.widenessToThicknessRatio);
            }
          }
        }
      ]), h;
    }(ya);
  }
  var SS = Sc();
  Sc({
    arrowHead: Ea
  });
  Sc({
    arrowHead: Js(Js({}, Ea), {}, {
      extremity: "both"
    })
  });
  const Zg = (e) => {
    const t = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(e);
    return t ? {
      r: parseInt(t[1], 16),
      g: parseInt(t[2], 16),
      b: parseInt(t[3], 16)
    } : {
      r: 100,
      g: 100,
      b: 100
    };
  }, qg = (e, t, n) => "#" + [
    e,
    t,
    n
  ].map((r) => {
    const i = Math.max(0, Math.min(255, Math.round(r))).toString(16);
    return i.length === 1 ? "0" + i : i;
  }).join(""), hl = (e, t) => {
    const n = Zg(e), r = {
      r: 18,
      g: 18,
      b: 28
    };
    return qg(r.r + (n.r - r.r) * t, r.g + (n.g - r.g) * t, r.b + (n.b - r.b) * t);
  }, _S = (e, t) => {
    const n = Zg(e);
    return qg(n.r + (255 - n.r) * (t - 1) / t, n.g + (255 - n.g) * (t - 1) / t, n.b + (255 - n.b) * (t - 1) / t);
  }, kS = {
    maxIterations: 20,
    ratio: 1.1,
    margin: 10,
    expansion: 1.05
  }, bS = (e) => {
    const t = e < 500, n = e >= 500 && e < 2e3, r = e >= 2e3 && e < 1e4;
    return {
      gravity: t ? 0.8 : n ? 0.5 : r ? 0.3 : 0.15,
      scalingRatio: t ? 15 : n ? 30 : r ? 60 : 100,
      slowDown: t ? 1 : n ? 2 : r ? 3 : 5,
      barnesHutOptimize: e > 200,
      barnesHutTheta: r ? 0.8 : 0.6,
      strongGravityMode: false,
      outboundAttractionDistribution: true,
      linLogMode: false,
      adjustSizes: true,
      edgeWeightInfluence: 1
    };
  }, xS = (e = {}) => {
    const t = z.useRef(null), n = z.useRef(null), r = z.useRef(null), i = z.useRef(null), o = z.useRef(null), s = z.useRef(/* @__PURE__ */ new Set()), a = z.useRef(/* @__PURE__ */ new Set()), l = z.useRef(/* @__PURE__ */ new Map()), c = z.useRef(null), h = z.useRef(null), f = z.useRef(null), [p, y] = z.useState(false), [k, b] = z.useState(null);
    z.useEffect(() => {
      var _a2;
      s.current = e.highlightedNodeIds || /* @__PURE__ */ new Set(), a.current = e.blastRadiusNodeIds || /* @__PURE__ */ new Set(), l.current = e.animatedNodes || /* @__PURE__ */ new Map(), c.current = e.visibleEdgeTypes || null, (_a2 = n.current) == null ? void 0 : _a2.refresh();
    }, [
      e.highlightedNodeIds,
      e.blastRadiusNodeIds,
      e.animatedNodes,
      e.visibleEdgeTypes
    ]), z.useEffect(() => {
      if (!e.animatedNodes || e.animatedNodes.size === 0) {
        f.current && (cancelAnimationFrame(f.current), f.current = null);
        return;
      }
      const N = () => {
        var _a2;
        (_a2 = n.current) == null ? void 0 : _a2.refresh(), f.current = requestAnimationFrame(N);
      };
      return N(), () => {
        f.current && (cancelAnimationFrame(f.current), f.current = null);
      };
    }, [
      e.animatedNodes
    ]);
    const I = z.useCallback((N) => {
      o.current = N, b(N);
      const V = n.current;
      if (!V) return;
      const B = V.getCamera(), K = B.ratio;
      B.animate({
        ratio: K * 1.0001
      }, {
        duration: 50
      }), V.refresh();
    }, []);
    z.useEffect(() => {
      if (!t.current) return;
      const N = new Pe();
      r.current = N;
      const V = new kE(N, t.current, {
        renderLabels: true,
        labelFont: "JetBrains Mono, monospace",
        labelSize: 11,
        labelWeight: "500",
        labelColor: {
          color: "#e4e4ed"
        },
        labelRenderedSizeThreshold: 8,
        labelDensity: 0.1,
        labelGridCellSize: 70,
        renderEdgeLabels: false,
        enableEdgeEvents: false,
        defaultNodeColor: "#6b7280",
        defaultEdgeColor: "#2a2a3a",
        defaultEdgeType: "curved",
        edgeProgramClasses: {
          curved: SS
        },
        defaultDrawNodeHover: (B, K, O) => {
          const re = K.label;
          if (!re) return;
          const ae = O.labelSize || 11, J = O.labelFont || "JetBrains Mono, monospace", S = O.labelWeight || "500";
          B.font = `${S} ${ae}px ${J}`;
          const j = B.measureText(re).width, H = K.size || 8, D = K.x, x = K.y - H - 10, Q = 8, _e = ae + 5 * 2, Se = j + Q * 2, oe = 4;
          B.fillStyle = "#12121c", B.beginPath(), B.roundRect(D - Se / 2, x - _e / 2, Se, _e, oe), B.fill(), B.strokeStyle = K.color || "#6366f1", B.lineWidth = 2, B.stroke(), B.fillStyle = "#f5f5f7", B.textAlign = "center", B.textBaseline = "middle", B.fillText(re, D, x), B.beginPath(), B.arc(K.x, K.y, H + 4, 0, Math.PI * 2), B.strokeStyle = K.color || "#6366f1", B.lineWidth = 2, B.globalAlpha = 0.5, B.stroke(), B.globalAlpha = 1;
        },
        minCameraRatio: 2e-3,
        maxCameraRatio: 50,
        hideEdgesOnMove: true,
        zIndex: true,
        nodeReducer: (B, K) => {
          const O = {
            ...K
          };
          if (K.hidden) return O.hidden = true, O;
          const re = o.current, ae = s.current, J = a.current, S = l.current, j = ae.size > 0, H = J.size > 0, D = ae.has(B), x = J.has(B), Q = S.get(B);
          if (Q) {
            const _e = Date.now() - Q.startTime, Se = Math.min(_e / Q.duration, 1), oe = (Math.sin(Se * Math.PI * 4) + 1) / 2;
            if (Q.type === "pulse") {
              const Z = 1.5 + oe * 0.8;
              O.size = (K.size || 8) * Z, O.color = oe > 0.5 ? "#06b6d4" : _S("#06b6d4", 1.3), O.zIndex = 5, O.highlighted = true;
            } else if (Q.type === "ripple") {
              const Z = 1.3 + oe * 1.2;
              O.size = (K.size || 8) * Z, O.color = oe > 0.5 ? "#ef4444" : "#f87171", O.zIndex = 5, O.highlighted = true;
            } else if (Q.type === "glow") {
              const Z = 1.4 + oe * 0.6;
              O.size = (K.size || 8) * Z, O.color = oe > 0.5 ? "#a855f7" : "#c084fc", O.zIndex = 5, O.highlighted = true;
            }
            return O;
          }
          if (H && !re) return x ? (O.color = "#ef4444", O.size = (K.size || 8) * 1.8, O.zIndex = 3, O.highlighted = true) : D ? (O.color = "#06b6d4", O.size = (K.size || 8) * 1.4, O.zIndex = 2, O.highlighted = true) : (O.color = hl(K.color, 0.15), O.size = (K.size || 8) * 0.4, O.zIndex = 0), O;
          if (j && !re) return D ? (O.color = "#06b6d4", O.size = (K.size || 8) * 1.6, O.zIndex = 2, O.highlighted = true) : (O.color = hl(K.color, 0.2), O.size = (K.size || 8) * 0.5, O.zIndex = 0), O;
          if (re) {
            const ie = r.current;
            if (ie) {
              const _e = B === re, Se = ie.hasEdge(B, re) || ie.hasEdge(re, B);
              _e ? (O.color = K.color, O.size = (K.size || 8) * 1.8, O.zIndex = 2, O.highlighted = true) : Se ? (O.color = K.color, O.size = (K.size || 8) * 1.3, O.zIndex = 1) : (O.color = hl(K.color, 0.25), O.size = (K.size || 8) * 0.6, O.zIndex = 0);
            }
          }
          return O;
        },
        edgeReducer: (B, K) => ({
          hidden: true
        })
      });
      return n.current = V, V.on("clickNode", ({ node: B }) => {
        var _a2;
        I(B), (_a2 = e.onNodeClick) == null ? void 0 : _a2.call(e, B);
      }), V.on("clickStage", () => {
        var _a2;
        I(null), (_a2 = e.onStageClick) == null ? void 0 : _a2.call(e);
      }), V.on("enterNode", ({ node: B }) => {
        var _a2;
        (_a2 = e.onNodeHover) == null ? void 0 : _a2.call(e, B), t.current && (t.current.style.cursor = "pointer");
      }), V.on("leaveNode", () => {
        var _a2;
        (_a2 = e.onNodeHover) == null ? void 0 : _a2.call(e, null), t.current && (t.current.style.cursor = "grab");
      }), () => {
        var _a2;
        h.current && clearTimeout(h.current), (_a2 = i.current) == null ? void 0 : _a2.kill(), V.kill(), n.current = null, r.current = null;
      };
    }, []);
    const _ = z.useCallback((N) => {
      const V = N.order;
      if (V === 0) return;
      i.current && (i.current.kill(), i.current = null), h.current && (clearTimeout(h.current), h.current = null);
      const B = Q1.inferSettings(N), K = bS(V), O = {
        ...B,
        ...K
      }, re = new O1(N, {
        settings: O
      });
      i.current = re, re.start(), y(true);
    }, []), m = z.useCallback((N) => {
      const V = n.current;
      V && (i.current && (i.current.kill(), i.current = null), h.current && (clearTimeout(h.current), h.current = null), r.current = N, V.setGraph(N), I(null), _(N), V.getCamera().animatedReset({
        duration: 500
      }));
    }, [
      _,
      I
    ]), v = z.useCallback((N) => {
      const V = n.current, B = r.current;
      if (!V || !B || !B.hasNode(N)) return;
      const K = o.current === N;
      if (o.current = N, b(N), !K) {
        const O = B.getNodeAttributes(N);
        V.getCamera().animate({
          x: O.x,
          y: O.y,
          ratio: 0.15
        }, {
          duration: 400
        });
      }
      V.refresh();
    }, []), E = z.useCallback(() => {
      var _a2;
      (_a2 = n.current) == null ? void 0 : _a2.getCamera().animatedZoom({
        duration: 200
      });
    }, []), A = z.useCallback(() => {
      var _a2;
      (_a2 = n.current) == null ? void 0 : _a2.getCamera().animatedUnzoom({
        duration: 200
      });
    }, []), F = z.useCallback(() => {
      var _a2;
      (_a2 = n.current) == null ? void 0 : _a2.getCamera().animatedReset({
        duration: 300
      }), I(null);
    }, [
      I
    ]), R = z.useCallback(() => {
      const N = r.current;
      !N || N.order === 0 || _(N);
    }, [
      _
    ]), L = z.useCallback(() => {
      var _a2;
      if (h.current && (clearTimeout(h.current), h.current = null), i.current) {
        i.current.stop(), i.current = null;
        const N = r.current;
        N && (iS.assign(N, kS), (_a2 = n.current) == null ? void 0 : _a2.refresh()), y(false);
      }
    }, []), C = z.useCallback(() => {
      var _a2;
      (_a2 = n.current) == null ? void 0 : _a2.refresh();
    }, []);
    return {
      containerRef: t,
      sigmaRef: n,
      setGraph: m,
      zoomIn: E,
      zoomOut: A,
      resetZoom: F,
      focusNode: v,
      isLayoutRunning: p,
      startLayout: R,
      stopLayout: L,
      selectedNode: k,
      setSelectedNode: I,
      refreshHighlights: C
    };
  }, bf = (e, t) => t > 5e4 ? Math.max(1, e * 0.4) : t > 2e4 ? Math.max(1.5, e * 0.5) : t > 5e3 ? Math.max(2, e * 0.65) : t > 1e3 ? Math.max(2.5, e * 0.8) : e, xf = (e, t) => {
    const n = t > 5e3 ? 2 : t > 1e3 ? 1.5 : 1;
    switch (e) {
      case "Project":
        return 50 * n;
      case "Package":
        return 30 * n;
      case "Module":
        return 20 * n;
      case "Folder":
        return 15 * n;
      case "File":
        return 3 * n;
      case "Class":
      case "Interface":
        return 5 * n;
      case "Function":
      case "Method":
        return 2 * n;
      default:
        return 1;
    }
  }, CS = (e, t) => {
    const n = new Pe(), r = e.nodes.length, i = /* @__PURE__ */ new Map(), o = /* @__PURE__ */ new Map(), s = /* @__PURE__ */ new Set([
      "CONTAINS",
      "DEFINES",
      "IMPORTS"
    ]);
    e.relationships.forEach((E) => {
      s.has(E.type) && (i.has(E.sourceId) || i.set(E.sourceId, []), i.get(E.sourceId).push(E.targetId), o.set(E.targetId, E.sourceId));
    });
    const a = new Map(e.nodes.map((E) => [
      E.id,
      E
    ])), l = /* @__PURE__ */ new Set([
      "Project",
      "Package",
      "Module",
      "Folder"
    ]), c = e.nodes.filter((E) => l.has(E.label)), h = Math.sqrt(r) * 40, f = Math.sqrt(r) * 3, p = /* @__PURE__ */ new Map();
    if (t && t.size > 0) {
      const E = new Set(t.values()), A = E.size, F = h * 0.8, R = Math.PI * (3 - Math.sqrt(5));
      let L = 0;
      E.forEach((C) => {
        const N = L * R, V = F * Math.sqrt((L + 1) / A);
        p.set(C, {
          x: V * Math.cos(N),
          y: V * Math.sin(N)
        }), L++;
      });
    }
    const y = Math.sqrt(r) * 1.5, k = /* @__PURE__ */ new Map();
    c.forEach((E, A) => {
      const F = Math.PI * (3 - Math.sqrt(5)), R = A * F, L = h * Math.sqrt((A + 1) / Math.max(c.length, 1)), C = h * 0.15, N = L * Math.cos(R) + (Math.random() - 0.5) * C, V = L * Math.sin(R) + (Math.random() - 0.5) * C;
      k.set(E.id, {
        x: N,
        y: V
      });
      const B = Od[E.label] || 8, K = bf(B, r);
      n.addNode(E.id, {
        x: N,
        y: V,
        size: K,
        color: zd[E.label] || "#9ca3af",
        label: E.properties.name,
        nodeType: E.label,
        filePath: E.properties.filePath,
        startLine: E.properties.startLine,
        endLine: E.properties.endLine,
        hidden: false,
        mass: xf(E.label, r)
      });
    });
    const b = (E) => {
      if (n.hasNode(E)) return;
      const A = a.get(E);
      if (!A) return;
      let F, R;
      const L = t == null ? void 0 : t.get(E), C = /* @__PURE__ */ new Set([
        "Function",
        "Class",
        "Method",
        "Interface"
      ]), N = L !== void 0 ? p.get(L) : null;
      if (N && C.has(A.label)) F = N.x + (Math.random() - 0.5) * y, R = N.y + (Math.random() - 0.5) * y;
      else {
        const ae = o.get(E), J = ae ? k.get(ae) : null;
        J ? (F = J.x + (Math.random() - 0.5) * f, R = J.y + (Math.random() - 0.5) * f) : (F = (Math.random() - 0.5) * h * 0.5, R = (Math.random() - 0.5) * h * 0.5);
      }
      k.set(E, {
        x: F,
        y: R
      });
      const V = Od[A.label] || 8, B = bf(V, r), K = L !== void 0, re = K && C.has(A.label) ? Ud(L) : zd[A.label] || "#9ca3af";
      n.addNode(E, {
        x: F,
        y: R,
        size: B,
        color: re,
        label: A.properties.name,
        nodeType: A.label,
        filePath: A.properties.filePath,
        startLine: A.properties.startLine,
        endLine: A.properties.endLine,
        hidden: false,
        mass: xf(A.label, r),
        community: L,
        communityColor: K ? Ud(L) : void 0
      });
    }, I = [
      ...c.map((E) => E.id)
    ], _ = new Set(I);
    for (; I.length > 0; ) {
      const E = I.shift(), A = i.get(E) || [];
      for (const F of A) _.has(F) || (_.add(F), b(F), I.push(F));
    }
    e.nodes.forEach((E) => {
      n.hasNode(E.id) || b(E.id);
    });
    const m = r > 2e4 ? 0.4 : r > 5e3 ? 0.6 : 1, v = {
      CONTAINS: {
        color: "#2d5a3d",
        sizeMultiplier: 0.4
      },
      DEFINES: {
        color: "#0e7490",
        sizeMultiplier: 0.5
      },
      IMPORTS: {
        color: "#1d4ed8",
        sizeMultiplier: 0.6
      },
      CALLS: {
        color: "#7c3aed",
        sizeMultiplier: 0.8
      },
      EXTENDS: {
        color: "#c2410c",
        sizeMultiplier: 1
      },
      IMPLEMENTS: {
        color: "#be185d",
        sizeMultiplier: 0.9
      }
    };
    return e.relationships.forEach((E) => {
      if (n.hasNode(E.sourceId) && n.hasNode(E.targetId) && !n.hasEdge(E.sourceId, E.targetId)) {
        const A = v[E.type] || {
          color: "#4a4a5a",
          sizeMultiplier: 0.5
        }, F = 0.12 + Math.random() * 0.08;
        n.addEdge(E.sourceId, E.targetId, {
          size: m * A.sizeMultiplier,
          color: A.color,
          relationType: E.type,
          type: "curved",
          curvature: F
        });
      }
    }), n;
  }, Cf = (e, t) => {
    e.forEachNode((n, r) => {
      const i = t.includes(r.nodeType);
      e.setNodeAttribute(n, "hidden", !i);
    });
  }, TS = (e, t, n) => {
    const r = /* @__PURE__ */ new Set(), i = [
      {
        nodeId: t,
        depth: 0
      }
    ];
    for (; i.length > 0; ) {
      const { nodeId: o, depth: s } = i.shift();
      r.has(o) || (r.add(o), s < n && e.forEachNeighbor(o, (a) => {
        r.has(a) || i.push({
          nodeId: a,
          depth: s + 1
        });
      }));
    }
    return r;
  }, RS = (e, t, n, r) => {
    if (n === null) {
      Cf(e, r);
      return;
    }
    if (t === null || !e.hasNode(t)) {
      Cf(e, r);
      return;
    }
    const i = TS(e, t, n);
    e.forEachNode((o, s) => {
      const a = r.includes(s.nodeType), l = i.has(o);
      e.setNodeAttribute(o, "hidden", !a || !l);
    });
  }, AS = [
    {
      label: "All Functions",
      query: "MATCH (n:Function) RETURN n.id AS id, n.name AS name, n.filePath AS path LIMIT 50"
    },
    {
      label: "All Classes",
      query: "MATCH (n:Class) RETURN n.id AS id, n.name AS name, n.filePath AS path LIMIT 50"
    },
    {
      label: "All Interfaces",
      query: "MATCH (n:Interface) RETURN n.id AS id, n.name AS name, n.filePath AS path LIMIT 50"
    },
    {
      label: "Function Calls",
      query: "MATCH (a:File)-[r:CodeRelation {type: 'CALLS'}]->(b:Function) RETURN a.id AS id, a.name AS caller, b.name AS callee LIMIT 50"
    },
    {
      label: "Import Dependencies",
      query: "MATCH (a:File)-[r:CodeRelation {type: 'IMPORTS'}]->(b:File) RETURN a.id AS id, a.name AS from, b.name AS imports LIMIT 50"
    }
  ], LS = () => {
    const { setHighlightedNodeIds: e, setQueryResult: t, queryResult: n, clearQueryHighlights: r, graph: i, runQuery: o, isDatabaseReady: s } = fc(), [a, l] = z.useState(false), [c, h] = z.useState(""), [f, p] = z.useState(false), [y, k] = z.useState(null), [b, I] = z.useState(false), [_, m] = z.useState(true), v = z.useRef(null), E = z.useRef(null);
    z.useEffect(() => {
      a && v.current && v.current.focus();
    }, [
      a
    ]), z.useEffect(() => {
      const N = (V) => {
        E.current && !E.current.contains(V.target) && I(false);
      };
      return document.addEventListener("mousedown", N), () => document.removeEventListener("mousedown", N);
    }, []), z.useEffect(() => {
      const N = (V) => {
        V.key === "Escape" && a && (l(false), I(false));
      };
      return document.addEventListener("keydown", N), () => document.removeEventListener("keydown", N);
    }, [
      a
    ]);
    const A = z.useCallback(async () => {
      if (!c.trim() || f) return;
      if (!i) {
        k("No project loaded. Load a project first.");
        return;
      }
      if (!await s()) {
        k("Database not ready. Please wait for loading to complete.");
        return;
      }
      p(true), k(null);
      const V = performance.now();
      try {
        const B = await o(c), K = performance.now() - V, O = /^(File|Function|Class|Method|Interface|Folder|CodeElement):/, re = B.flatMap((ae) => {
          const J = [];
          return Array.isArray(ae) ? ae.forEach((S) => {
            typeof S == "string" && (O.test(S) || S.includes(":")) && J.push(S);
          }) : typeof ae == "object" && ae !== null && Object.entries(ae).forEach(([S, j]) => {
            const H = S.toLowerCase();
            typeof j == "string" && (H.includes("id") || H === "id" || O.test(j)) && J.push(j);
          }), J;
        }).filter(Boolean).filter((ae, J, S) => S.indexOf(ae) === J);
        t({
          rows: B,
          nodeIds: re,
          executionTime: K
        }), e(new Set(re));
      } catch (B) {
        k(B instanceof Error ? B.message : "Query execution failed"), t(null), e(/* @__PURE__ */ new Set());
      } finally {
        p(false);
      }
    }, [
      c,
      f,
      i,
      s,
      o,
      e,
      t
    ]), F = (N) => {
      N.key === "Enter" && (N.ctrlKey || N.metaKey) && (N.preventDefault(), A());
    }, R = (N) => {
      var _a2;
      h(N), I(false), (_a2 = v.current) == null ? void 0 : _a2.focus();
    }, L = () => {
      l(false), I(false), r(), k(null);
    }, C = () => {
      var _a2;
      h(""), r(), k(null), (_a2 = v.current) == null ? void 0 : _a2.focus();
    };
    return a ? M.jsxs("div", {
      ref: E,
      className: `\r
        absolute bottom-4 left-4 z-20\r
        w-[480px] max-w-[calc(100%-2rem)]\r
        bg-deep/95 backdrop-blur-md\r
        border border-cyan-500/30\r
        rounded-xl\r
        shadow-[0_0_40px_rgba(6,182,212,0.2)]\r
        animate-fade-in\r
      `,
      children: [
        M.jsxs("div", {
          className: "flex items-center justify-between px-4 py-3 border-b border-border-subtle",
          children: [
            M.jsxs("div", {
              className: "flex items-center gap-2",
              children: [
                M.jsx("div", {
                  className: "w-7 h-7 flex items-center justify-center bg-[#3C7FF5] rounded-lg",
                  children: M.jsx($d, {
                    className: "w-4 h-4 text-white"
                  })
                }),
                M.jsx("span", {
                  className: "font-medium text-sm",
                  children: "Cypher Query"
                })
              ]
            }),
            M.jsx("button", {
              onClick: L,
              className: "p-1.5 text-text-muted hover:text-text-primary hover:bg-hover rounded-md transition-colors",
              children: M.jsx(Y0, {
                className: "w-4 h-4"
              })
            })
          ]
        }),
        M.jsxs("div", {
          className: "p-3",
          children: [
            M.jsx("div", {
              className: "relative",
              children: M.jsx("textarea", {
                ref: v,
                value: c,
                onChange: (N) => h(N.target.value),
                onKeyDown: F,
                placeholder: "MATCH (n:Function) RETURN n.name, n.filePath LIMIT 10",
                rows: 3,
                className: `\r
              w-full px-3 py-2.5\r
              bg-surface border border-border-subtle rounded-lg\r
              text-sm font-mono text-text-primary\r
              placeholder:text-text-muted\r
              focus:border-cyan-500/50 focus:ring-2 focus:ring-cyan-500/20\r
              outline-none resize-none\r
              transition-all\r
            `
              })
            }),
            M.jsxs("div", {
              className: "flex items-center justify-between mt-3",
              children: [
                M.jsxs("div", {
                  className: "relative",
                  children: [
                    M.jsxs("button", {
                      onClick: () => I(!b),
                      className: `\r
                flex items-center gap-1.5 px-3 py-1.5\r
                text-xs text-text-secondary\r
                hover:text-text-primary hover:bg-hover\r
                rounded-md transition-colors\r
              `,
                      children: [
                        M.jsx(j0, {
                          className: "w-3.5 h-3.5"
                        }),
                        M.jsx("span", {
                          children: "Examples"
                        }),
                        M.jsx(Md, {
                          className: `w-3.5 h-3.5 transition-transform ${b ? "rotate-180" : ""}`
                        })
                      ]
                    }),
                    b && M.jsx("div", {
                      className: `\r
                absolute bottom-full left-0 mb-2\r
                w-64 py-1\r
                bg-surface border border-border-subtle rounded-lg\r
                shadow-xl\r
                animate-fade-in\r
              `,
                      children: AS.map((N) => M.jsx("button", {
                        onClick: () => R(N.query),
                        className: `\r
                      w-full px-3 py-2 text-left\r
                      text-sm text-text-secondary\r
                      hover:bg-hover hover:text-text-primary\r
                      transition-colors\r
                    `,
                        children: N.label
                      }, N.label))
                    })
                  ]
                }),
                M.jsxs("div", {
                  className: "flex items-center gap-2",
                  children: [
                    c && M.jsx("button", {
                      onClick: C,
                      className: `\r
                  px-3 py-1.5\r
                  text-xs text-text-secondary\r
                  hover:text-text-primary hover:bg-hover\r
                  rounded-md transition-colors\r
                `,
                      children: "Clear"
                    }),
                    M.jsxs("button", {
                      onClick: A,
                      disabled: !c.trim() || f,
                      className: `\r
                flex items-center gap-1.5 px-4 py-1.5\r
                bg-[#3C7FF5]\r
                rounded-md text-white text-sm font-medium\r
                shadow-[0_0_15px_rgba(60,127,245,0.3)]\r
                hover:shadow-[0_0_20px_rgba(60,127,245,0.5)]\r
                disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none\r
                transition-all\r
              `,
                      children: [
                        f ? M.jsx(O0, {
                          className: "w-3.5 h-3.5 animate-spin"
                        }) : M.jsx(U0, {
                          className: "w-3.5 h-3.5"
                        }),
                        M.jsx("span", {
                          children: "Run"
                        }),
                        M.jsx("kbd", {
                          className: "ml-1 px-1 py-0.5 bg-white/20 rounded text-[10px]",
                          children: "\u2318\u21B5"
                        })
                      ]
                    })
                  ]
                })
              ]
            })
          ]
        }),
        y && M.jsx("div", {
          className: "px-4 py-2 bg-red-500/10 border-t border-red-500/20",
          children: M.jsx("p", {
            className: "text-xs text-red-400 font-mono",
            children: y
          })
        }),
        n && !y && M.jsxs("div", {
          className: "border-t border-cyan-500/20",
          children: [
            M.jsxs("div", {
              className: "px-4 py-2.5 bg-cyan-500/5 flex items-center justify-between",
              children: [
                M.jsxs("div", {
                  className: "flex items-center gap-3 text-xs",
                  children: [
                    M.jsxs("span", {
                      className: "text-text-secondary",
                      children: [
                        M.jsx("span", {
                          className: "text-cyan-400 font-semibold",
                          children: n.rows.length
                        }),
                        " rows"
                      ]
                    }),
                    n.nodeIds.length > 0 && M.jsxs("span", {
                      className: "text-text-secondary",
                      children: [
                        M.jsx("span", {
                          className: "text-cyan-400 font-semibold",
                          children: n.nodeIds.length
                        }),
                        " highlighted"
                      ]
                    }),
                    M.jsxs("span", {
                      className: "text-text-muted",
                      children: [
                        n.executionTime.toFixed(1),
                        "ms"
                      ]
                    })
                  ]
                }),
                M.jsxs("div", {
                  className: "flex items-center gap-2",
                  children: [
                    n.nodeIds.length > 0 && M.jsx("button", {
                      onClick: r,
                      className: "text-xs text-text-muted hover:text-text-primary transition-colors",
                      children: "Clear"
                    }),
                    M.jsxs("button", {
                      onClick: () => m(!_),
                      className: "flex items-center gap-1 text-xs text-text-muted hover:text-text-primary transition-colors",
                      children: [
                        M.jsx(W0, {
                          className: "w-3 h-3"
                        }),
                        _ ? M.jsx(Md, {
                          className: "w-3 h-3"
                        }) : M.jsx(P0, {
                          className: "w-3 h-3"
                        })
                      ]
                    })
                  ]
                })
              ]
            }),
            _ && n.rows.length > 0 && M.jsxs("div", {
              className: "max-h-48 overflow-auto scrollbar-thin border-t border-border-subtle",
              children: [
                M.jsxs("table", {
                  className: "w-full text-xs",
                  children: [
                    M.jsx("thead", {
                      className: "bg-surface sticky top-0",
                      children: M.jsx("tr", {
                        children: Object.keys(n.rows[0]).map((N) => M.jsx("th", {
                          className: "px-3 py-2 text-left text-text-muted font-medium border-b border-border-subtle",
                          children: N
                        }, N))
                      })
                    }),
                    M.jsx("tbody", {
                      children: n.rows.slice(0, 50).map((N, V) => M.jsx("tr", {
                        className: "hover:bg-hover/50 transition-colors",
                        children: Object.values(N).map((B, K) => M.jsx("td", {
                          className: "px-3 py-1.5 text-text-secondary border-b border-border-subtle/50 font-mono truncate max-w-[200px]",
                          children: typeof B == "object" ? JSON.stringify(B) : String(B ?? "")
                        }, K))
                      }, V))
                    })
                  ]
                }),
                n.rows.length > 50 && M.jsxs("div", {
                  className: "px-3 py-2 text-xs text-text-muted bg-surface border-t border-border-subtle",
                  children: [
                    "Showing 50 of ",
                    n.rows.length,
                    " rows"
                  ]
                })
              ]
            })
          ]
        })
      ]
    }) : M.jsxs("button", {
      onClick: () => l(true),
      className: `\r
          group absolute bottom-4 left-4 z-20\r
          flex items-center gap-2 px-4 py-2.5\r
          bg-[#3C7FF5]\r
          rounded-xl text-white font-medium text-sm\r
          shadow-[0_0_20px_rgba(60,127,245,0.4)]\r
          hover:shadow-[0_0_30px_rgba(60,127,245,0.6)]\r
          hover:-translate-y-0.5\r
          transition-all duration-200\r
        `,
      children: [
        M.jsx($d, {
          className: "w-4 h-4"
        }),
        M.jsx("span", {
          children: "Query"
        }),
        n && n.nodeIds.length > 0 && M.jsx("span", {
          className: `\r
            px-1.5 py-0.5 ml-1\r
            bg-white/20 rounded-md\r
            text-xs font-semibold\r
          `,
          children: n.nodeIds.length
        })
      ]
    });
  }, Jg = z.forwardRef(({ background: e = "dark" }, t) => {
    const { graph: n, setSelectedNode: r, selectedNode: i, visibleLabels: o, visibleEdgeTypes: s, openCodePanel: a, depthFilter: l, highlightedNodeIds: c, setHighlightedNodeIds: h, aiCitationHighlightedNodeIds: f, aiToolHighlightedNodeIds: p, blastRadiusNodeIds: y, isAIHighlightsEnabled: k, toggleAIHighlights: b, animatedNodes: I } = fc(), [_, m] = z.useState(null), v = e === "light", E = z.useMemo(() => {
      if (!k) return c;
      const j = new Set(c);
      for (const H of f) j.add(H);
      for (const H of p) j.add(H);
      return j;
    }, [
      c,
      f,
      p,
      k
    ]), A = z.useMemo(() => k ? y : /* @__PURE__ */ new Set(), [
      y,
      k
    ]), F = z.useMemo(() => k ? I : /* @__PURE__ */ new Map(), [
      I,
      k
    ]), R = z.useCallback((j) => {
      if (!n) return;
      const H = n.nodes.find((D) => D.id === j);
      H && (r(H), a());
    }, [
      n,
      r,
      a
    ]), L = z.useCallback((j) => {
      if (!j || !n) {
        m(null);
        return;
      }
      const H = n.nodes.find((D) => D.id === j);
      H && m(H.properties.name);
    }, [
      n
    ]), C = z.useCallback(() => {
      r(null);
    }, [
      r
    ]), { containerRef: N, sigmaRef: V, setGraph: B, resetZoom: K, focusNode: O, selectedNode: re, setSelectedNode: ae } = xS({
      onNodeClick: R,
      onNodeHover: L,
      onStageClick: C,
      highlightedNodeIds: E,
      blastRadiusNodeIds: A,
      animatedNodes: F,
      visibleEdgeTypes: s
    });
    z.useImperativeHandle(t, () => ({
      focusNode: (j) => {
        if (n) {
          const H = n.nodes.find((D) => D.id === j);
          H && (r(H), a());
        }
        O(j);
      }
    }), [
      O,
      n,
      r,
      a
    ]), z.useEffect(() => {
      if (!n) return;
      const j = /* @__PURE__ */ new Map();
      n.relationships.forEach((D) => {
        if (D.type === "MEMBER_OF" && n.nodes.find((Q) => Q.id === D.targetId && Q.label === "Community")) {
          const Q = parseInt(D.targetId.replace("comm_", ""), 10) || 0;
          j.set(D.sourceId, Q);
        }
      });
      const H = CS(n, j);
      B(H);
    }, [
      n,
      B
    ]), z.useEffect(() => {
      const j = V.current;
      if (!j) return;
      const H = j.getGraph();
      H.order !== 0 && (RS(H, (i == null ? void 0 : i.id) || null, l, o), j.refresh());
    }, [
      o,
      l,
      i,
      V
    ]), z.useEffect(() => {
      ae(i ? i.id : null);
    }, [
      i,
      ae
    ]);
    const J = z.useCallback(() => {
      i && O(i.id);
    }, [
      i,
      O
    ]), S = z.useCallback(() => {
      r(null), ae(null), K();
    }, [
      r,
      ae,
      K
    ]);
    return M.jsxs("div", {
      className: `relative w-full h-full ${v ? "bg-white" : "bg-void"}`,
      children: [
        M.jsx("div", {
          className: "absolute inset-0 pointer-events-none",
          children: M.jsx("div", {
            className: "absolute inset-0",
            style: {
              background: v ? `
                radial-gradient(circle at 50% 50%, rgba(124, 58, 237, 0.06) 0%, transparent 70%),
                linear-gradient(to bottom, #ffffff, #f5f5f5)
              ` : `
                radial-gradient(circle at 50% 50%, rgba(124, 58, 237, 0.03) 0%, transparent 70%),
                linear-gradient(to bottom, #06060a, #0a0a10)
              `
            }
          })
        }),
        M.jsx("div", {
          ref: N,
          className: "sigma-container w-full h-full cursor-grab active:cursor-grabbing"
        }),
        _ && !re && M.jsx("div", {
          className: "absolute top-4 left-1/2 -translate-x-1/2 px-3 py-1.5 bg-elevated/95 border border-border-subtle rounded-lg backdrop-blur-sm z-20 pointer-events-none animate-fade-in",
          children: M.jsx("span", {
            className: "font-mono text-sm text-text-primary",
            children: _
          })
        }),
        re && i && M.jsxs("div", {
          className: "absolute top-4 left-1/2 -translate-x-1/2 flex items-center gap-2 px-4 py-2 bg-accent/20 border border-accent/30 rounded-xl backdrop-blur-sm z-20 animate-slide-up",
          children: [
            M.jsx("div", {
              className: "w-2 h-2 bg-accent rounded-full animate-pulse"
            }),
            M.jsx("span", {
              className: "font-mono text-sm text-text-primary",
              children: i.properties.name
            }),
            M.jsxs("span", {
              className: "text-xs text-text-muted",
              children: [
                "(",
                i.label,
                ")"
              ]
            }),
            M.jsx("button", {
              onClick: S,
              className: "ml-2 px-2 py-0.5 text-xs text-text-secondary hover:text-text-primary hover:bg-white/10 rounded transition-colors",
              children: "Clear"
            })
          ]
        }),
        M.jsxs("div", {
          className: "absolute bottom-4 right-4 flex flex-col gap-1 z-10",
          children: [
            M.jsx("div", {
              className: "h-px bg-border-subtle my-1"
            }),
            i && M.jsx("button", {
              onClick: J,
              className: "w-9 h-9 flex items-center justify-center bg-accent/20 border border-accent/30 rounded-md text-accent hover:bg-accent/30 transition-colors",
              title: "Focus on Selected Node",
              children: M.jsx(F0, {
                className: "w-4 h-4"
              })
            }),
            re && M.jsx("button", {
              onClick: S,
              className: "w-9 h-9 flex items-center justify-center bg-elevated border border-border-subtle rounded-md text-text-secondary hover:bg-hover hover:text-text-primary transition-colors",
              title: "Clear Selection",
              children: M.jsx(M0, {
                className: "w-4 h-4"
              })
            }),
            M.jsx("div", {
              className: "h-px bg-border-subtle my-1"
            })
          ]
        }),
        M.jsx(LS, {}),
        M.jsx("div", {
          className: "absolute top-4 right-4 z-20"
        })
      ]
    });
  });
  Jg.displayName = "GraphCanvas";
  let mu = null;
  try {
    mu = (await r0(async () => {
      const { default: e } = await import("./GraphCache-BoqPIAC4.js");
      return {
        default: e
      };
    }, [])).default;
  } catch {
  }
  const IS = () => {
    const { viewMode: e, setViewMode: t, setGraph: n, setFileContents: r, setProgress: i, setProjectName: o, progress: s, runPipeline: a, initializeAgent: l, startEmbeddings: c } = fc(), h = z.useRef(null), [f, p] = z.useState("dark");
    z.useEffect(() => {
      const k = (b) => {
        var _a2;
        ((_a2 = b.data) == null ? void 0 : _a2.type) === "THEME_CHANGE" && p(b.data.theme === "light" ? "light" : "dark");
      };
      return window.addEventListener("message", k), () => window.removeEventListener("message", k);
    }, []), z.useEffect(() => {
      if (!mu) return;
      const { graph: k, fileContents: b, projectName: I } = mu;
      n(k), r(b), t("exploring"), I && o(I), Zs() && l(I ?? ""), c().catch(console.warn);
    }, []);
    const y = z.useCallback(async (k) => {
      const b = k.name.replace(".zip", "");
      o(b), i({
        phase: "extracting",
        percent: 0,
        message: "Starting...",
        detail: "Preparing to extract files"
      }), t("loading");
      try {
        const I = await a(k, (_) => {
          i(_);
        });
        console.log("============================"), console.log(I), n(I.graph), r(I.fileContents), t("exploring"), Zs() && l(b), c().catch((_) => {
          var _a2;
          (_ == null ? void 0 : _.name) === "WebGPUNotAvailableError" || ((_a2 = _ == null ? void 0 : _.message) == null ? void 0 : _a2.includes("WebGPU")) ? c("wasm").catch(console.warn) : console.warn("Embeddings auto-start failed:", _);
        });
      } catch (I) {
        console.error("Pipeline error:", I), i({
          phase: "error",
          percent: 0,
          message: "Error processing file",
          detail: I instanceof Error ? I.message : "Unknown error"
        }), setTimeout(() => {
          t("onboarding"), i(null);
        }, 3e3);
      }
    }, [
      t,
      n,
      r,
      i,
      o,
      a,
      c,
      l
    ]);
    return e === "onboarding" ? M.jsx(b0, {
      onFileSelect: y
    }) : e === "loading" && s ? M.jsx(x0, {
      progress: s
    }) : M.jsx("div", {
      className: "flex flex-col h-screen bg-void overflow-hidden",
      children: M.jsx("main", {
        className: "flex-1 flex min-h-0",
        children: M.jsx("div", {
          className: "flex-1 relative min-w-0",
          children: M.jsx(Jg, {
            ref: h,
            background: f
          })
        })
      })
    });
  };
  function DS() {
    return M.jsx(k0, {
      children: M.jsx(IS, {})
    });
  }
  globalThis.Buffer = Up.Buffer;
  pl.createRoot(document.getElementById("root")).render(M.jsx(Fm.StrictMode, {
    children: M.jsx(DS, {})
  }));
})();
