(async () => {
  (function() {
    const t = document.createElement("link").relList;
    if (t && t.supports && t.supports("modulepreload")) return;
    for (const i of document.querySelectorAll('link[rel="modulepreload"]')) r(i);
    new MutationObserver((i) => {
      for (const o of i) if (o.type === "childList") for (const a of o.addedNodes) a.tagName === "LINK" && a.rel === "modulepreload" && r(a);
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
  function xo(e) {
    return e && e.__esModule && Object.prototype.hasOwnProperty.call(e, "default") ? e.default : e;
  }
  var kf = {
    exports: {}
  }, Ja = {}, bf = {
    exports: {}
  }, Ee = {};
  var To = Symbol.for("react.element"), vm = Symbol.for("react.portal"), ym = Symbol.for("react.fragment"), wm = Symbol.for("react.strict_mode"), Em = Symbol.for("react.profiler"), Sm = Symbol.for("react.provider"), _m = Symbol.for("react.context"), km = Symbol.for("react.forward_ref"), bm = Symbol.for("react.suspense"), Cm = Symbol.for("react.memo"), xm = Symbol.for("react.lazy"), _c = Symbol.iterator;
  function Tm(e) {
    return e === null || typeof e != "object" ? null : (e = _c && e[_c] || e["@@iterator"], typeof e == "function" ? e : null);
  }
  var Cf = {
    isMounted: function() {
      return false;
    },
    enqueueForceUpdate: function() {
    },
    enqueueReplaceState: function() {
    },
    enqueueSetState: function() {
    }
  }, xf = Object.assign, Tf = {};
  function yi(e, t, n) {
    this.props = e, this.context = t, this.refs = Tf, this.updater = n || Cf;
  }
  yi.prototype.isReactComponent = {};
  yi.prototype.setState = function(e, t) {
    if (typeof e != "object" && typeof e != "function" && e != null) throw Error("setState(...): takes an object of state variables to update or a function which returns an object of state variables.");
    this.updater.enqueueSetState(this, e, t, "setState");
  };
  yi.prototype.forceUpdate = function(e) {
    this.updater.enqueueForceUpdate(this, e, "forceUpdate");
  };
  function Rf() {
  }
  Rf.prototype = yi.prototype;
  function mu(e, t, n) {
    this.props = e, this.context = t, this.refs = Tf, this.updater = n || Cf;
  }
  var vu = mu.prototype = new Rf();
  vu.constructor = mu;
  xf(vu, yi.prototype);
  vu.isPureReactComponent = true;
  var kc = Array.isArray, Af = Object.prototype.hasOwnProperty, yu = {
    current: null
  }, Lf = {
    key: true,
    ref: true,
    __self: true,
    __source: true
  };
  function Df(e, t, n) {
    var r, i = {}, o = null, a = null;
    if (t != null) for (r in t.ref !== void 0 && (a = t.ref), t.key !== void 0 && (o = "" + t.key), t) Af.call(t, r) && !Lf.hasOwnProperty(r) && (i[r] = t[r]);
    var s = arguments.length - 2;
    if (s === 1) i.children = n;
    else if (1 < s) {
      for (var l = Array(s), c = 0; c < s; c++) l[c] = arguments[c + 2];
      i.children = l;
    }
    if (e && e.defaultProps) for (r in s = e.defaultProps, s) i[r] === void 0 && (i[r] = s[r]);
    return {
      $$typeof: To,
      type: e,
      key: o,
      ref: a,
      props: i,
      _owner: yu.current
    };
  }
  function Rm(e, t) {
    return {
      $$typeof: To,
      type: e.type,
      key: t,
      ref: e.ref,
      props: e.props,
      _owner: e._owner
    };
  }
  function wu(e) {
    return typeof e == "object" && e !== null && e.$$typeof === To;
  }
  function Am(e) {
    var t = {
      "=": "=0",
      ":": "=2"
    };
    return "$" + e.replace(/[=:]/g, function(n) {
      return t[n];
    });
  }
  var bc = /\/+/g;
  function Cs(e, t) {
    return typeof e == "object" && e !== null && e.key != null ? Am("" + e.key) : t.toString(36);
  }
  function la(e, t, n, r, i) {
    var o = typeof e;
    (o === "undefined" || o === "boolean") && (e = null);
    var a = false;
    if (e === null) a = true;
    else switch (o) {
      case "string":
      case "number":
        a = true;
        break;
      case "object":
        switch (e.$$typeof) {
          case To:
          case vm:
            a = true;
        }
    }
    if (a) return a = e, i = i(a), e = r === "" ? "." + Cs(a, 0) : r, kc(i) ? (n = "", e != null && (n = e.replace(bc, "$&/") + "/"), la(i, t, n, "", function(c) {
      return c;
    })) : i != null && (wu(i) && (i = Rm(i, n + (!i.key || a && a.key === i.key ? "" : ("" + i.key).replace(bc, "$&/") + "/") + e)), t.push(i)), 1;
    if (a = 0, r = r === "" ? "." : r + ":", kc(e)) for (var s = 0; s < e.length; s++) {
      o = e[s];
      var l = r + Cs(o, s);
      a += la(o, t, n, l, i);
    }
    else if (l = Tm(e), typeof l == "function") for (e = l.call(e), s = 0; !(o = e.next()).done; ) o = o.value, l = r + Cs(o, s++), a += la(o, t, n, l, i);
    else if (o === "object") throw t = String(e), Error("Objects are not valid as a React child (found: " + (t === "[object Object]" ? "object with keys {" + Object.keys(e).join(", ") + "}" : t) + "). If you meant to render a collection of children, use an array instead.");
    return a;
  }
  function zo(e, t, n) {
    if (e == null) return e;
    var r = [], i = 0;
    return la(e, r, "", "", function(o) {
      return t.call(n, o, i++);
    }), r;
  }
  function Lm(e) {
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
  var Dt = {
    current: null
  }, ua = {
    transition: null
  }, Dm = {
    ReactCurrentDispatcher: Dt,
    ReactCurrentBatchConfig: ua,
    ReactCurrentOwner: yu
  };
  function Pf() {
    throw Error("act(...) is not supported in production builds of React.");
  }
  Ee.Children = {
    map: zo,
    forEach: function(e, t, n) {
      zo(e, function() {
        t.apply(this, arguments);
      }, n);
    },
    count: function(e) {
      var t = 0;
      return zo(e, function() {
        t++;
      }), t;
    },
    toArray: function(e) {
      return zo(e, function(t) {
        return t;
      }) || [];
    },
    only: function(e) {
      if (!wu(e)) throw Error("React.Children.only expected to receive a single React element child.");
      return e;
    }
  };
  Ee.Component = yi;
  Ee.Fragment = ym;
  Ee.Profiler = Em;
  Ee.PureComponent = mu;
  Ee.StrictMode = wm;
  Ee.Suspense = bm;
  Ee.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED = Dm;
  Ee.act = Pf;
  Ee.cloneElement = function(e, t, n) {
    if (e == null) throw Error("React.cloneElement(...): The argument must be a React element, but you passed " + e + ".");
    var r = xf({}, e.props), i = e.key, o = e.ref, a = e._owner;
    if (t != null) {
      if (t.ref !== void 0 && (o = t.ref, a = yu.current), t.key !== void 0 && (i = "" + t.key), e.type && e.type.defaultProps) var s = e.type.defaultProps;
      for (l in t) Af.call(t, l) && !Lf.hasOwnProperty(l) && (r[l] = t[l] === void 0 && s !== void 0 ? s[l] : t[l]);
    }
    var l = arguments.length - 2;
    if (l === 1) r.children = n;
    else if (1 < l) {
      s = Array(l);
      for (var c = 0; c < l; c++) s[c] = arguments[c + 2];
      r.children = s;
    }
    return {
      $$typeof: To,
      type: e.type,
      key: i,
      ref: o,
      props: r,
      _owner: a
    };
  };
  Ee.createContext = function(e) {
    return e = {
      $$typeof: _m,
      _currentValue: e,
      _currentValue2: e,
      _threadCount: 0,
      Provider: null,
      Consumer: null,
      _defaultValue: null,
      _globalName: null
    }, e.Provider = {
      $$typeof: Sm,
      _context: e
    }, e.Consumer = e;
  };
  Ee.createElement = Df;
  Ee.createFactory = function(e) {
    var t = Df.bind(null, e);
    return t.type = e, t;
  };
  Ee.createRef = function() {
    return {
      current: null
    };
  };
  Ee.forwardRef = function(e) {
    return {
      $$typeof: km,
      render: e
    };
  };
  Ee.isValidElement = wu;
  Ee.lazy = function(e) {
    return {
      $$typeof: xm,
      _payload: {
        _status: -1,
        _result: e
      },
      _init: Lm
    };
  };
  Ee.memo = function(e, t) {
    return {
      $$typeof: Cm,
      type: e,
      compare: t === void 0 ? null : t
    };
  };
  Ee.startTransition = function(e) {
    var t = ua.transition;
    ua.transition = {};
    try {
      e();
    } finally {
      ua.transition = t;
    }
  };
  Ee.unstable_act = Pf;
  Ee.useCallback = function(e, t) {
    return Dt.current.useCallback(e, t);
  };
  Ee.useContext = function(e) {
    return Dt.current.useContext(e);
  };
  Ee.useDebugValue = function() {
  };
  Ee.useDeferredValue = function(e) {
    return Dt.current.useDeferredValue(e);
  };
  Ee.useEffect = function(e, t) {
    return Dt.current.useEffect(e, t);
  };
  Ee.useId = function() {
    return Dt.current.useId();
  };
  Ee.useImperativeHandle = function(e, t, n) {
    return Dt.current.useImperativeHandle(e, t, n);
  };
  Ee.useInsertionEffect = function(e, t) {
    return Dt.current.useInsertionEffect(e, t);
  };
  Ee.useLayoutEffect = function(e, t) {
    return Dt.current.useLayoutEffect(e, t);
  };
  Ee.useMemo = function(e, t) {
    return Dt.current.useMemo(e, t);
  };
  Ee.useReducer = function(e, t, n) {
    return Dt.current.useReducer(e, t, n);
  };
  Ee.useRef = function(e) {
    return Dt.current.useRef(e);
  };
  Ee.useState = function(e) {
    return Dt.current.useState(e);
  };
  Ee.useSyncExternalStore = function(e, t, n) {
    return Dt.current.useSyncExternalStore(e, t, n);
  };
  Ee.useTransition = function() {
    return Dt.current.useTransition();
  };
  Ee.version = "18.3.1";
  bf.exports = Ee;
  var N = bf.exports;
  const Pm = xo(N);
  var Im = N, Fm = Symbol.for("react.element"), Nm = Symbol.for("react.fragment"), zm = Object.prototype.hasOwnProperty, Om = Im.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentOwner, Gm = {
    key: true,
    ref: true,
    __self: true,
    __source: true
  };
  function If(e, t, n) {
    var r, i = {}, o = null, a = null;
    n !== void 0 && (o = "" + n), t.key !== void 0 && (o = "" + t.key), t.ref !== void 0 && (a = t.ref);
    for (r in t) zm.call(t, r) && !Gm.hasOwnProperty(r) && (i[r] = t[r]);
    if (e && e.defaultProps) for (r in t = e.defaultProps, t) i[r] === void 0 && (i[r] = t[r]);
    return {
      $$typeof: Fm,
      type: e,
      key: o,
      ref: a,
      props: i,
      _owner: Om.current
    };
  }
  Ja.Fragment = Nm;
  Ja.jsx = If;
  Ja.jsxs = If;
  kf.exports = Ja;
  var q = kf.exports, hl = {}, Ff = {
    exports: {}
  }, Kt = {}, Nf = {
    exports: {}
  }, zf = {};
  (function(e) {
    function t(_, $) {
      var H = _.length;
      _.push($);
      e: for (; 0 < H; ) {
        var D = H - 1 >>> 1, C = _[D];
        if (0 < i(C, $)) _[D] = $, _[H] = C, H = D;
        else break e;
      }
    }
    function n(_) {
      return _.length === 0 ? null : _[0];
    }
    function r(_) {
      if (_.length === 0) return null;
      var $ = _[0], H = _.pop();
      if (H !== $) {
        _[0] = H;
        e: for (var D = 0, C = _.length, Y = C >>> 1; D < Y; ) {
          var ie = 2 * (D + 1) - 1, _e = _[ie], Se = ie + 1, oe = _[Se];
          if (0 > i(_e, H)) Se < C && 0 > i(oe, _e) ? (_[D] = oe, _[Se] = H, D = Se) : (_[D] = _e, _[ie] = H, D = ie);
          else if (Se < C && 0 > i(oe, H)) _[D] = oe, _[Se] = H, D = Se;
          else break e;
        }
      }
      return $;
    }
    function i(_, $) {
      var H = _.sortIndex - $.sortIndex;
      return H !== 0 ? H : _.id - $.id;
    }
    if (typeof performance == "object" && typeof performance.now == "function") {
      var o = performance;
      e.unstable_now = function() {
        return o.now();
      };
    } else {
      var a = Date, s = a.now();
      e.unstable_now = function() {
        return a.now() - s;
      };
    }
    var l = [], c = [], h = 1, f = null, p = 3, y = false, k = false, b = false, I = typeof setTimeout == "function" ? setTimeout : null, S = typeof clearTimeout == "function" ? clearTimeout : null, m = typeof setImmediate < "u" ? setImmediate : null;
    typeof navigator < "u" && navigator.scheduling !== void 0 && navigator.scheduling.isInputPending !== void 0 && navigator.scheduling.isInputPending.bind(navigator.scheduling);
    function v(_) {
      for (var $ = n(c); $ !== null; ) {
        if ($.callback === null) r(c);
        else if ($.startTime <= _) r(c), $.sortIndex = $.expirationTime, t(l, $);
        else break;
        $ = n(c);
      }
    }
    function E(_) {
      if (b = false, v(_), !k) if (n(l) !== null) k = true, fe(A);
      else {
        var $ = n(c);
        $ !== null && te(E, $.startTime - _);
      }
    }
    function A(_, $) {
      k = false, b && (b = false, S(L), L = -1), y = true;
      var H = p;
      try {
        for (v($), f = n(l); f !== null && (!(f.expirationTime > $) || _ && !V()); ) {
          var D = f.callback;
          if (typeof D == "function") {
            f.callback = null, p = f.priorityLevel;
            var C = D(f.expirationTime <= $);
            $ = e.unstable_now(), typeof C == "function" ? f.callback = C : f === n(l) && r(l), v($);
          } else r(l);
          f = n(l);
        }
        if (f !== null) var Y = true;
        else {
          var ie = n(c);
          ie !== null && te(E, ie.startTime - $), Y = false;
        }
        return Y;
      } finally {
        f = null, p = H, y = false;
      }
    }
    var F = false, R = null, L = -1, x = 5, G = -1;
    function V() {
      return !(e.unstable_now() - G < x);
    }
    function B() {
      if (R !== null) {
        var _ = e.unstable_now();
        G = _;
        var $ = true;
        try {
          $ = R(true, _);
        } finally {
          $ ? W() : (F = false, R = null);
        }
      } else F = false;
    }
    var W;
    if (typeof m == "function") W = function() {
      m(B);
    };
    else if (typeof MessageChannel < "u") {
      var O = new MessageChannel(), re = O.port2;
      O.port1.onmessage = B, W = function() {
        re.postMessage(null);
      };
    } else W = function() {
      I(B, 0);
    };
    function fe(_) {
      R = _, F || (F = true, W());
    }
    function te(_, $) {
      L = I(function() {
        _(e.unstable_now());
      }, $);
    }
    e.unstable_IdlePriority = 5, e.unstable_ImmediatePriority = 1, e.unstable_LowPriority = 4, e.unstable_NormalPriority = 3, e.unstable_Profiling = null, e.unstable_UserBlockingPriority = 2, e.unstable_cancelCallback = function(_) {
      _.callback = null;
    }, e.unstable_continueExecution = function() {
      k || y || (k = true, fe(A));
    }, e.unstable_forceFrameRate = function(_) {
      0 > _ || 125 < _ ? console.error("forceFrameRate takes a positive int between 0 and 125, forcing frame rates higher than 125 fps is not supported") : x = 0 < _ ? Math.floor(1e3 / _) : 5;
    }, e.unstable_getCurrentPriorityLevel = function() {
      return p;
    }, e.unstable_getFirstCallbackNode = function() {
      return n(l);
    }, e.unstable_next = function(_) {
      switch (p) {
        case 1:
        case 2:
        case 3:
          var $ = 3;
          break;
        default:
          $ = p;
      }
      var H = p;
      p = $;
      try {
        return _();
      } finally {
        p = H;
      }
    }, e.unstable_pauseExecution = function() {
    }, e.unstable_requestPaint = function() {
    }, e.unstable_runWithPriority = function(_, $) {
      switch (_) {
        case 1:
        case 2:
        case 3:
        case 4:
        case 5:
          break;
        default:
          _ = 3;
      }
      var H = p;
      p = _;
      try {
        return $();
      } finally {
        p = H;
      }
    }, e.unstable_scheduleCallback = function(_, $, H) {
      var D = e.unstable_now();
      switch (typeof H == "object" && H !== null ? (H = H.delay, H = typeof H == "number" && 0 < H ? D + H : D) : H = D, _) {
        case 1:
          var C = -1;
          break;
        case 2:
          C = 250;
          break;
        case 5:
          C = 1073741823;
          break;
        case 4:
          C = 1e4;
          break;
        default:
          C = 5e3;
      }
      return C = H + C, _ = {
        id: h++,
        callback: $,
        priorityLevel: _,
        startTime: H,
        expirationTime: C,
        sortIndex: -1
      }, H > D ? (_.sortIndex = H, t(c, _), n(l) === null && _ === n(c) && (b ? (S(L), L = -1) : b = true, te(E, H - D))) : (_.sortIndex = C, t(l, _), k || y || (k = true, fe(A))), _;
    }, e.unstable_shouldYield = V, e.unstable_wrapCallback = function(_) {
      var $ = p;
      return function() {
        var H = p;
        p = $;
        try {
          return _.apply(this, arguments);
        } finally {
          p = H;
        }
      };
    };
  })(zf);
  Nf.exports = zf;
  var Um = Nf.exports;
  var Bm = N, Vt = Um;
  function j(e) {
    for (var t = "https://reactjs.org/docs/error-decoder.html?invariant=" + e, n = 1; n < arguments.length; n++) t += "&args[]=" + encodeURIComponent(arguments[n]);
    return "Minified React error #" + e + "; visit " + t + " for the full message or use the non-minified dev environment for full errors and additional helpful warnings.";
  }
  var Of = /* @__PURE__ */ new Set(), so = {};
  function zr(e, t) {
    li(e, t), li(e + "Capture", t);
  }
  function li(e, t) {
    for (so[e] = t, e = 0; e < t.length; e++) Of.add(t[e]);
  }
  var jn = !(typeof window > "u" || typeof window.document > "u" || typeof window.document.createElement > "u"), pl = Object.prototype.hasOwnProperty, Mm = /^[:A-Z_a-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD][:A-Z_a-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD\-.0-9\u00B7\u0300-\u036F\u203F-\u2040]*$/, Cc = {}, xc = {};
  function $m(e) {
    return pl.call(xc, e) ? true : pl.call(Cc, e) ? false : Mm.test(e) ? xc[e] = true : (Cc[e] = true, false);
  }
  function jm(e, t, n, r) {
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
  function Hm(e, t, n, r) {
    if (t === null || typeof t > "u" || jm(e, t, n, r)) return true;
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
  function Pt(e, t, n, r, i, o, a) {
    this.acceptsBooleans = t === 2 || t === 3 || t === 4, this.attributeName = r, this.attributeNamespace = i, this.mustUseProperty = n, this.propertyName = e, this.type = t, this.sanitizeURL = o, this.removeEmptyString = a;
  }
  var gt = {};
  "children dangerouslySetInnerHTML defaultValue defaultChecked innerHTML suppressContentEditableWarning suppressHydrationWarning style".split(" ").forEach(function(e) {
    gt[e] = new Pt(e, 0, false, e, null, false, false);
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
    gt[t] = new Pt(t, 1, false, e[1], null, false, false);
  });
  [
    "contentEditable",
    "draggable",
    "spellCheck",
    "value"
  ].forEach(function(e) {
    gt[e] = new Pt(e, 2, false, e.toLowerCase(), null, false, false);
  });
  [
    "autoReverse",
    "externalResourcesRequired",
    "focusable",
    "preserveAlpha"
  ].forEach(function(e) {
    gt[e] = new Pt(e, 2, false, e, null, false, false);
  });
  "allowFullScreen async autoFocus autoPlay controls default defer disabled disablePictureInPicture disableRemotePlayback formNoValidate hidden loop noModule noValidate open playsInline readOnly required reversed scoped seamless itemScope".split(" ").forEach(function(e) {
    gt[e] = new Pt(e, 3, false, e.toLowerCase(), null, false, false);
  });
  [
    "checked",
    "multiple",
    "muted",
    "selected"
  ].forEach(function(e) {
    gt[e] = new Pt(e, 3, true, e, null, false, false);
  });
  [
    "capture",
    "download"
  ].forEach(function(e) {
    gt[e] = new Pt(e, 4, false, e, null, false, false);
  });
  [
    "cols",
    "rows",
    "size",
    "span"
  ].forEach(function(e) {
    gt[e] = new Pt(e, 6, false, e, null, false, false);
  });
  [
    "rowSpan",
    "start"
  ].forEach(function(e) {
    gt[e] = new Pt(e, 5, false, e.toLowerCase(), null, false, false);
  });
  var Eu = /[\-:]([a-z])/g;
  function Su(e) {
    return e[1].toUpperCase();
  }
  "accent-height alignment-baseline arabic-form baseline-shift cap-height clip-path clip-rule color-interpolation color-interpolation-filters color-profile color-rendering dominant-baseline enable-background fill-opacity fill-rule flood-color flood-opacity font-family font-size font-size-adjust font-stretch font-style font-variant font-weight glyph-name glyph-orientation-horizontal glyph-orientation-vertical horiz-adv-x horiz-origin-x image-rendering letter-spacing lighting-color marker-end marker-mid marker-start overline-position overline-thickness paint-order panose-1 pointer-events rendering-intent shape-rendering stop-color stop-opacity strikethrough-position strikethrough-thickness stroke-dasharray stroke-dashoffset stroke-linecap stroke-linejoin stroke-miterlimit stroke-opacity stroke-width text-anchor text-decoration text-rendering underline-position underline-thickness unicode-bidi unicode-range units-per-em v-alphabetic v-hanging v-ideographic v-mathematical vector-effect vert-adv-y vert-origin-x vert-origin-y word-spacing writing-mode xmlns:xlink x-height".split(" ").forEach(function(e) {
    var t = e.replace(Eu, Su);
    gt[t] = new Pt(t, 1, false, e, null, false, false);
  });
  "xlink:actuate xlink:arcrole xlink:role xlink:show xlink:title xlink:type".split(" ").forEach(function(e) {
    var t = e.replace(Eu, Su);
    gt[t] = new Pt(t, 1, false, e, "http://www.w3.org/1999/xlink", false, false);
  });
  [
    "xml:base",
    "xml:lang",
    "xml:space"
  ].forEach(function(e) {
    var t = e.replace(Eu, Su);
    gt[t] = new Pt(t, 1, false, e, "http://www.w3.org/XML/1998/namespace", false, false);
  });
  [
    "tabIndex",
    "crossOrigin"
  ].forEach(function(e) {
    gt[e] = new Pt(e, 1, false, e.toLowerCase(), null, false, false);
  });
  gt.xlinkHref = new Pt("xlinkHref", 1, false, "xlink:href", "http://www.w3.org/1999/xlink", true, false);
  [
    "src",
    "href",
    "action",
    "formAction"
  ].forEach(function(e) {
    gt[e] = new Pt(e, 1, false, e.toLowerCase(), null, true, true);
  });
  function _u(e, t, n, r) {
    var i = gt.hasOwnProperty(t) ? gt[t] : null;
    (i !== null ? i.type !== 0 : r || !(2 < t.length) || t[0] !== "o" && t[0] !== "O" || t[1] !== "n" && t[1] !== "N") && (Hm(t, n, i, r) && (n = null), r || i === null ? $m(t) && (n === null ? e.removeAttribute(t) : e.setAttribute(t, "" + n)) : i.mustUseProperty ? e[i.propertyName] = n === null ? i.type === 3 ? false : "" : n : (t = i.attributeName, r = i.attributeNamespace, n === null ? e.removeAttribute(t) : (i = i.type, n = i === 3 || i === 4 && n === true ? "" : "" + n, r ? e.setAttributeNS(r, t, n) : e.setAttribute(t, n))));
  }
  var Kn = Bm.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED, Oo = Symbol.for("react.element"), $r = Symbol.for("react.portal"), jr = Symbol.for("react.fragment"), ku = Symbol.for("react.strict_mode"), gl = Symbol.for("react.profiler"), Gf = Symbol.for("react.provider"), Uf = Symbol.for("react.context"), bu = Symbol.for("react.forward_ref"), ml = Symbol.for("react.suspense"), vl = Symbol.for("react.suspense_list"), Cu = Symbol.for("react.memo"), tr = Symbol.for("react.lazy"), Bf = Symbol.for("react.offscreen"), Tc = Symbol.iterator;
  function Ri(e) {
    return e === null || typeof e != "object" ? null : (e = Tc && e[Tc] || e["@@iterator"], typeof e == "function" ? e : null);
  }
  var je = Object.assign, xs;
  function Vi(e) {
    if (xs === void 0) try {
      throw Error();
    } catch (n) {
      var t = n.stack.trim().match(/\n( *(at )?)/);
      xs = t && t[1] || "";
    }
    return `
` + xs + e;
  }
  var Ts = false;
  function Rs(e, t) {
    if (!e || Ts) return "";
    Ts = true;
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
`), a = i.length - 1, s = o.length - 1; 1 <= a && 0 <= s && i[a] !== o[s]; ) s--;
        for (; 1 <= a && 0 <= s; a--, s--) if (i[a] !== o[s]) {
          if (a !== 1 || s !== 1) do
            if (a--, s--, 0 > s || i[a] !== o[s]) {
              var l = `
` + i[a].replace(" at new ", " at ");
              return e.displayName && l.includes("<anonymous>") && (l = l.replace("<anonymous>", e.displayName)), l;
            }
          while (1 <= a && 0 <= s);
          break;
        }
      }
    } finally {
      Ts = false, Error.prepareStackTrace = n;
    }
    return (e = e ? e.displayName || e.name : "") ? Vi(e) : "";
  }
  function Wm(e) {
    switch (e.tag) {
      case 5:
        return Vi(e.type);
      case 16:
        return Vi("Lazy");
      case 13:
        return Vi("Suspense");
      case 19:
        return Vi("SuspenseList");
      case 0:
      case 2:
      case 15:
        return e = Rs(e.type, false), e;
      case 11:
        return e = Rs(e.type.render, false), e;
      case 1:
        return e = Rs(e.type, true), e;
      default:
        return "";
    }
  }
  function yl(e) {
    if (e == null) return null;
    if (typeof e == "function") return e.displayName || e.name || null;
    if (typeof e == "string") return e;
    switch (e) {
      case jr:
        return "Fragment";
      case $r:
        return "Portal";
      case gl:
        return "Profiler";
      case ku:
        return "StrictMode";
      case ml:
        return "Suspense";
      case vl:
        return "SuspenseList";
    }
    if (typeof e == "object") switch (e.$$typeof) {
      case Uf:
        return (e.displayName || "Context") + ".Consumer";
      case Gf:
        return (e._context.displayName || "Context") + ".Provider";
      case bu:
        var t = e.render;
        return e = e.displayName, e || (e = t.displayName || t.name || "", e = e !== "" ? "ForwardRef(" + e + ")" : "ForwardRef"), e;
      case Cu:
        return t = e.displayName || null, t !== null ? t : yl(e.type) || "Memo";
      case tr:
        t = e._payload, e = e._init;
        try {
          return yl(e(t));
        } catch {
        }
    }
    return null;
  }
  function Vm(e) {
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
        return yl(t);
      case 8:
        return t === ku ? "StrictMode" : "Mode";
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
  function gr(e) {
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
  function Mf(e) {
    var t = e.type;
    return (e = e.nodeName) && e.toLowerCase() === "input" && (t === "checkbox" || t === "radio");
  }
  function Km(e) {
    var t = Mf(e) ? "checked" : "value", n = Object.getOwnPropertyDescriptor(e.constructor.prototype, t), r = "" + e[t];
    if (!e.hasOwnProperty(t) && typeof n < "u" && typeof n.get == "function" && typeof n.set == "function") {
      var i = n.get, o = n.set;
      return Object.defineProperty(e, t, {
        configurable: true,
        get: function() {
          return i.call(this);
        },
        set: function(a) {
          r = "" + a, o.call(this, a);
        }
      }), Object.defineProperty(e, t, {
        enumerable: n.enumerable
      }), {
        getValue: function() {
          return r;
        },
        setValue: function(a) {
          r = "" + a;
        },
        stopTracking: function() {
          e._valueTracker = null, delete e[t];
        }
      };
    }
  }
  function Go(e) {
    e._valueTracker || (e._valueTracker = Km(e));
  }
  function $f(e) {
    if (!e) return false;
    var t = e._valueTracker;
    if (!t) return true;
    var n = t.getValue(), r = "";
    return e && (r = Mf(e) ? e.checked ? "true" : "false" : e.value), e = r, e !== n ? (t.setValue(e), true) : false;
  }
  function ka(e) {
    if (e = e || (typeof document < "u" ? document : void 0), typeof e > "u") return null;
    try {
      return e.activeElement || e.body;
    } catch {
      return e.body;
    }
  }
  function wl(e, t) {
    var n = t.checked;
    return je({}, t, {
      defaultChecked: void 0,
      defaultValue: void 0,
      value: void 0,
      checked: n ?? e._wrapperState.initialChecked
    });
  }
  function Rc(e, t) {
    var n = t.defaultValue == null ? "" : t.defaultValue, r = t.checked != null ? t.checked : t.defaultChecked;
    n = gr(t.value != null ? t.value : n), e._wrapperState = {
      initialChecked: r,
      initialValue: n,
      controlled: t.type === "checkbox" || t.type === "radio" ? t.checked != null : t.value != null
    };
  }
  function jf(e, t) {
    t = t.checked, t != null && _u(e, "checked", t, false);
  }
  function El(e, t) {
    jf(e, t);
    var n = gr(t.value), r = t.type;
    if (n != null) r === "number" ? (n === 0 && e.value === "" || e.value != n) && (e.value = "" + n) : e.value !== "" + n && (e.value = "" + n);
    else if (r === "submit" || r === "reset") {
      e.removeAttribute("value");
      return;
    }
    t.hasOwnProperty("value") ? Sl(e, t.type, n) : t.hasOwnProperty("defaultValue") && Sl(e, t.type, gr(t.defaultValue)), t.checked == null && t.defaultChecked != null && (e.defaultChecked = !!t.defaultChecked);
  }
  function Ac(e, t, n) {
    if (t.hasOwnProperty("value") || t.hasOwnProperty("defaultValue")) {
      var r = t.type;
      if (!(r !== "submit" && r !== "reset" || t.value !== void 0 && t.value !== null)) return;
      t = "" + e._wrapperState.initialValue, n || t === e.value || (e.value = t), e.defaultValue = t;
    }
    n = e.name, n !== "" && (e.name = ""), e.defaultChecked = !!e._wrapperState.initialChecked, n !== "" && (e.name = n);
  }
  function Sl(e, t, n) {
    (t !== "number" || ka(e.ownerDocument) !== e) && (n == null ? e.defaultValue = "" + e._wrapperState.initialValue : e.defaultValue !== "" + n && (e.defaultValue = "" + n));
  }
  var Ki = Array.isArray;
  function ei(e, t, n, r) {
    if (e = e.options, t) {
      t = {};
      for (var i = 0; i < n.length; i++) t["$" + n[i]] = true;
      for (n = 0; n < e.length; n++) i = t.hasOwnProperty("$" + e[n].value), e[n].selected !== i && (e[n].selected = i), i && r && (e[n].defaultSelected = true);
    } else {
      for (n = "" + gr(n), t = null, i = 0; i < e.length; i++) {
        if (e[i].value === n) {
          e[i].selected = true, r && (e[i].defaultSelected = true);
          return;
        }
        t !== null || e[i].disabled || (t = e[i]);
      }
      t !== null && (t.selected = true);
    }
  }
  function _l(e, t) {
    if (t.dangerouslySetInnerHTML != null) throw Error(j(91));
    return je({}, t, {
      value: void 0,
      defaultValue: void 0,
      children: "" + e._wrapperState.initialValue
    });
  }
  function Lc(e, t) {
    var n = t.value;
    if (n == null) {
      if (n = t.children, t = t.defaultValue, n != null) {
        if (t != null) throw Error(j(92));
        if (Ki(n)) {
          if (1 < n.length) throw Error(j(93));
          n = n[0];
        }
        t = n;
      }
      t == null && (t = ""), n = t;
    }
    e._wrapperState = {
      initialValue: gr(n)
    };
  }
  function Hf(e, t) {
    var n = gr(t.value), r = gr(t.defaultValue);
    n != null && (n = "" + n, n !== e.value && (e.value = n), t.defaultValue == null && e.defaultValue !== n && (e.defaultValue = n)), r != null && (e.defaultValue = "" + r);
  }
  function Dc(e) {
    var t = e.textContent;
    t === e._wrapperState.initialValue && t !== "" && t !== null && (e.value = t);
  }
  function Wf(e) {
    switch (e) {
      case "svg":
        return "http://www.w3.org/2000/svg";
      case "math":
        return "http://www.w3.org/1998/Math/MathML";
      default:
        return "http://www.w3.org/1999/xhtml";
    }
  }
  function kl(e, t) {
    return e == null || e === "http://www.w3.org/1999/xhtml" ? Wf(t) : e === "http://www.w3.org/2000/svg" && t === "foreignObject" ? "http://www.w3.org/1999/xhtml" : e;
  }
  var Uo, Vf = function(e) {
    return typeof MSApp < "u" && MSApp.execUnsafeLocalFunction ? function(t, n, r, i) {
      MSApp.execUnsafeLocalFunction(function() {
        return e(t, n, r, i);
      });
    } : e;
  }(function(e, t) {
    if (e.namespaceURI !== "http://www.w3.org/2000/svg" || "innerHTML" in e) e.innerHTML = t;
    else {
      for (Uo = Uo || document.createElement("div"), Uo.innerHTML = "<svg>" + t.valueOf().toString() + "</svg>", t = Uo.firstChild; e.firstChild; ) e.removeChild(e.firstChild);
      for (; t.firstChild; ) e.appendChild(t.firstChild);
    }
  });
  function lo(e, t) {
    if (t) {
      var n = e.firstChild;
      if (n && n === e.lastChild && n.nodeType === 3) {
        n.nodeValue = t;
        return;
      }
    }
    e.textContent = t;
  }
  var Zi = {
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
  }, Ym = [
    "Webkit",
    "ms",
    "Moz",
    "O"
  ];
  Object.keys(Zi).forEach(function(e) {
    Ym.forEach(function(t) {
      t = t + e.charAt(0).toUpperCase() + e.substring(1), Zi[t] = Zi[e];
    });
  });
  function Kf(e, t, n) {
    return t == null || typeof t == "boolean" || t === "" ? "" : n || typeof t != "number" || t === 0 || Zi.hasOwnProperty(e) && Zi[e] ? ("" + t).trim() : t + "px";
  }
  function Yf(e, t) {
    e = e.style;
    for (var n in t) if (t.hasOwnProperty(n)) {
      var r = n.indexOf("--") === 0, i = Kf(n, t[n], r);
      n === "float" && (n = "cssFloat"), r ? e.setProperty(n, i) : e[n] = i;
    }
  }
  var Qm = je({
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
  function bl(e, t) {
    if (t) {
      if (Qm[e] && (t.children != null || t.dangerouslySetInnerHTML != null)) throw Error(j(137, e));
      if (t.dangerouslySetInnerHTML != null) {
        if (t.children != null) throw Error(j(60));
        if (typeof t.dangerouslySetInnerHTML != "object" || !("__html" in t.dangerouslySetInnerHTML)) throw Error(j(61));
      }
      if (t.style != null && typeof t.style != "object") throw Error(j(62));
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
  var xl = null;
  function xu(e) {
    return e = e.target || e.srcElement || window, e.correspondingUseElement && (e = e.correspondingUseElement), e.nodeType === 3 ? e.parentNode : e;
  }
  var Tl = null, ti = null, ni = null;
  function Pc(e) {
    if (e = Lo(e)) {
      if (typeof Tl != "function") throw Error(j(280));
      var t = e.stateNode;
      t && (t = is(t), Tl(e.stateNode, e.type, t));
    }
  }
  function Qf(e) {
    ti ? ni ? ni.push(e) : ni = [
      e
    ] : ti = e;
  }
  function Xf() {
    if (ti) {
      var e = ti, t = ni;
      if (ni = ti = null, Pc(e), t) for (e = 0; e < t.length; e++) Pc(t[e]);
    }
  }
  function Zf(e, t) {
    return e(t);
  }
  function qf() {
  }
  var As = false;
  function Jf(e, t, n) {
    if (As) return e(t, n);
    As = true;
    try {
      return Zf(e, t, n);
    } finally {
      As = false, (ti !== null || ni !== null) && (qf(), Xf());
    }
  }
  function uo(e, t) {
    var n = e.stateNode;
    if (n === null) return null;
    var r = is(n);
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
    if (n && typeof n != "function") throw Error(j(231, t, typeof n));
    return n;
  }
  var Rl = false;
  if (jn) try {
    var Ai = {};
    Object.defineProperty(Ai, "passive", {
      get: function() {
        Rl = true;
      }
    }), window.addEventListener("test", Ai, Ai), window.removeEventListener("test", Ai, Ai);
  } catch {
    Rl = false;
  }
  function Xm(e, t, n, r, i, o, a, s, l) {
    var c = Array.prototype.slice.call(arguments, 3);
    try {
      t.apply(n, c);
    } catch (h) {
      this.onError(h);
    }
  }
  var qi = false, ba = null, Ca = false, Al = null, Zm = {
    onError: function(e) {
      qi = true, ba = e;
    }
  };
  function qm(e, t, n, r, i, o, a, s, l) {
    qi = false, ba = null, Xm.apply(Zm, arguments);
  }
  function Jm(e, t, n, r, i, o, a, s, l) {
    if (qm.apply(this, arguments), qi) {
      if (qi) {
        var c = ba;
        qi = false, ba = null;
      } else throw Error(j(198));
      Ca || (Ca = true, Al = c);
    }
  }
  function Or(e) {
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
  function eh(e) {
    if (e.tag === 13) {
      var t = e.memoizedState;
      if (t === null && (e = e.alternate, e !== null && (t = e.memoizedState)), t !== null) return t.dehydrated;
    }
    return null;
  }
  function Ic(e) {
    if (Or(e) !== e) throw Error(j(188));
  }
  function ev(e) {
    var t = e.alternate;
    if (!t) {
      if (t = Or(e), t === null) throw Error(j(188));
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
          if (o === n) return Ic(i), e;
          if (o === r) return Ic(i), t;
          o = o.sibling;
        }
        throw Error(j(188));
      }
      if (n.return !== r.return) n = i, r = o;
      else {
        for (var a = false, s = i.child; s; ) {
          if (s === n) {
            a = true, n = i, r = o;
            break;
          }
          if (s === r) {
            a = true, r = i, n = o;
            break;
          }
          s = s.sibling;
        }
        if (!a) {
          for (s = o.child; s; ) {
            if (s === n) {
              a = true, n = o, r = i;
              break;
            }
            if (s === r) {
              a = true, r = o, n = i;
              break;
            }
            s = s.sibling;
          }
          if (!a) throw Error(j(189));
        }
      }
      if (n.alternate !== r) throw Error(j(190));
    }
    if (n.tag !== 3) throw Error(j(188));
    return n.stateNode.current === n ? e : t;
  }
  function th(e) {
    return e = ev(e), e !== null ? nh(e) : null;
  }
  function nh(e) {
    if (e.tag === 5 || e.tag === 6) return e;
    for (e = e.child; e !== null; ) {
      var t = nh(e);
      if (t !== null) return t;
      e = e.sibling;
    }
    return null;
  }
  var rh = Vt.unstable_scheduleCallback, Fc = Vt.unstable_cancelCallback, tv = Vt.unstable_shouldYield, nv = Vt.unstable_requestPaint, Ze = Vt.unstable_now, rv = Vt.unstable_getCurrentPriorityLevel, Tu = Vt.unstable_ImmediatePriority, ih = Vt.unstable_UserBlockingPriority, xa = Vt.unstable_NormalPriority, iv = Vt.unstable_LowPriority, oh = Vt.unstable_IdlePriority, es = null, An = null;
  function ov(e) {
    if (An && typeof An.onCommitFiberRoot == "function") try {
      An.onCommitFiberRoot(es, e, void 0, (e.current.flags & 128) === 128);
    } catch {
    }
  }
  var wn = Math.clz32 ? Math.clz32 : lv, av = Math.log, sv = Math.LN2;
  function lv(e) {
    return e >>>= 0, e === 0 ? 32 : 31 - (av(e) / sv | 0) | 0;
  }
  var Bo = 64, Mo = 4194304;
  function Yi(e) {
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
  function Ta(e, t) {
    var n = e.pendingLanes;
    if (n === 0) return 0;
    var r = 0, i = e.suspendedLanes, o = e.pingedLanes, a = n & 268435455;
    if (a !== 0) {
      var s = a & ~i;
      s !== 0 ? r = Yi(s) : (o &= a, o !== 0 && (r = Yi(o)));
    } else a = n & ~i, a !== 0 ? r = Yi(a) : o !== 0 && (r = Yi(o));
    if (r === 0) return 0;
    if (t !== 0 && t !== r && !(t & i) && (i = r & -r, o = t & -t, i >= o || i === 16 && (o & 4194240) !== 0)) return t;
    if (r & 4 && (r |= n & 16), t = e.entangledLanes, t !== 0) for (e = e.entanglements, t &= r; 0 < t; ) n = 31 - wn(t), i = 1 << n, r |= e[n], t &= ~i;
    return r;
  }
  function uv(e, t) {
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
  function cv(e, t) {
    for (var n = e.suspendedLanes, r = e.pingedLanes, i = e.expirationTimes, o = e.pendingLanes; 0 < o; ) {
      var a = 31 - wn(o), s = 1 << a, l = i[a];
      l === -1 ? (!(s & n) || s & r) && (i[a] = uv(s, t)) : l <= t && (e.expiredLanes |= s), o &= ~s;
    }
  }
  function Ll(e) {
    return e = e.pendingLanes & -1073741825, e !== 0 ? e : e & 1073741824 ? 1073741824 : 0;
  }
  function ah() {
    var e = Bo;
    return Bo <<= 1, !(Bo & 4194240) && (Bo = 64), e;
  }
  function Ls(e) {
    for (var t = [], n = 0; 31 > n; n++) t.push(e);
    return t;
  }
  function Ro(e, t, n) {
    e.pendingLanes |= t, t !== 536870912 && (e.suspendedLanes = 0, e.pingedLanes = 0), e = e.eventTimes, t = 31 - wn(t), e[t] = n;
  }
  function dv(e, t) {
    var n = e.pendingLanes & ~t;
    e.pendingLanes = t, e.suspendedLanes = 0, e.pingedLanes = 0, e.expiredLanes &= t, e.mutableReadLanes &= t, e.entangledLanes &= t, t = e.entanglements;
    var r = e.eventTimes;
    for (e = e.expirationTimes; 0 < n; ) {
      var i = 31 - wn(n), o = 1 << i;
      t[i] = 0, r[i] = -1, e[i] = -1, n &= ~o;
    }
  }
  function Ru(e, t) {
    var n = e.entangledLanes |= t;
    for (e = e.entanglements; n; ) {
      var r = 31 - wn(n), i = 1 << r;
      i & t | e[r] & t && (e[r] |= t), n &= ~i;
    }
  }
  var Pe = 0;
  function sh(e) {
    return e &= -e, 1 < e ? 4 < e ? e & 268435455 ? 16 : 536870912 : 4 : 1;
  }
  var lh, Au, uh, ch, dh, Dl = false, $o = [], sr = null, lr = null, ur = null, co = /* @__PURE__ */ new Map(), fo = /* @__PURE__ */ new Map(), rr = [], fv = "mousedown mouseup touchcancel touchend touchstart auxclick dblclick pointercancel pointerdown pointerup dragend dragstart drop compositionend compositionstart keydown keypress keyup input textInput copy cut paste click change contextmenu reset submit".split(" ");
  function Nc(e, t) {
    switch (e) {
      case "focusin":
      case "focusout":
        sr = null;
        break;
      case "dragenter":
      case "dragleave":
        lr = null;
        break;
      case "mouseover":
      case "mouseout":
        ur = null;
        break;
      case "pointerover":
      case "pointerout":
        co.delete(t.pointerId);
        break;
      case "gotpointercapture":
      case "lostpointercapture":
        fo.delete(t.pointerId);
    }
  }
  function Li(e, t, n, r, i, o) {
    return e === null || e.nativeEvent !== o ? (e = {
      blockedOn: t,
      domEventName: n,
      eventSystemFlags: r,
      nativeEvent: o,
      targetContainers: [
        i
      ]
    }, t !== null && (t = Lo(t), t !== null && Au(t)), e) : (e.eventSystemFlags |= r, t = e.targetContainers, i !== null && t.indexOf(i) === -1 && t.push(i), e);
  }
  function hv(e, t, n, r, i) {
    switch (t) {
      case "focusin":
        return sr = Li(sr, e, t, n, r, i), true;
      case "dragenter":
        return lr = Li(lr, e, t, n, r, i), true;
      case "mouseover":
        return ur = Li(ur, e, t, n, r, i), true;
      case "pointerover":
        var o = i.pointerId;
        return co.set(o, Li(co.get(o) || null, e, t, n, r, i)), true;
      case "gotpointercapture":
        return o = i.pointerId, fo.set(o, Li(fo.get(o) || null, e, t, n, r, i)), true;
    }
    return false;
  }
  function fh(e) {
    var t = xr(e.target);
    if (t !== null) {
      var n = Or(t);
      if (n !== null) {
        if (t = n.tag, t === 13) {
          if (t = eh(n), t !== null) {
            e.blockedOn = t, dh(e.priority, function() {
              uh(n);
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
  function ca(e) {
    if (e.blockedOn !== null) return false;
    for (var t = e.targetContainers; 0 < t.length; ) {
      var n = Pl(e.domEventName, e.eventSystemFlags, t[0], e.nativeEvent);
      if (n === null) {
        n = e.nativeEvent;
        var r = new n.constructor(n.type, n);
        xl = r, n.target.dispatchEvent(r), xl = null;
      } else return t = Lo(n), t !== null && Au(t), e.blockedOn = n, false;
      t.shift();
    }
    return true;
  }
  function zc(e, t, n) {
    ca(e) && n.delete(t);
  }
  function pv() {
    Dl = false, sr !== null && ca(sr) && (sr = null), lr !== null && ca(lr) && (lr = null), ur !== null && ca(ur) && (ur = null), co.forEach(zc), fo.forEach(zc);
  }
  function Di(e, t) {
    e.blockedOn === t && (e.blockedOn = null, Dl || (Dl = true, Vt.unstable_scheduleCallback(Vt.unstable_NormalPriority, pv)));
  }
  function ho(e) {
    function t(i) {
      return Di(i, e);
    }
    if (0 < $o.length) {
      Di($o[0], e);
      for (var n = 1; n < $o.length; n++) {
        var r = $o[n];
        r.blockedOn === e && (r.blockedOn = null);
      }
    }
    for (sr !== null && Di(sr, e), lr !== null && Di(lr, e), ur !== null && Di(ur, e), co.forEach(t), fo.forEach(t), n = 0; n < rr.length; n++) r = rr[n], r.blockedOn === e && (r.blockedOn = null);
    for (; 0 < rr.length && (n = rr[0], n.blockedOn === null); ) fh(n), n.blockedOn === null && rr.shift();
  }
  var ri = Kn.ReactCurrentBatchConfig, Ra = true;
  function gv(e, t, n, r) {
    var i = Pe, o = ri.transition;
    ri.transition = null;
    try {
      Pe = 1, Lu(e, t, n, r);
    } finally {
      Pe = i, ri.transition = o;
    }
  }
  function mv(e, t, n, r) {
    var i = Pe, o = ri.transition;
    ri.transition = null;
    try {
      Pe = 4, Lu(e, t, n, r);
    } finally {
      Pe = i, ri.transition = o;
    }
  }
  function Lu(e, t, n, r) {
    if (Ra) {
      var i = Pl(e, t, n, r);
      if (i === null) Bs(e, t, r, Aa, n), Nc(e, r);
      else if (hv(i, e, t, n, r)) r.stopPropagation();
      else if (Nc(e, r), t & 4 && -1 < fv.indexOf(e)) {
        for (; i !== null; ) {
          var o = Lo(i);
          if (o !== null && lh(o), o = Pl(e, t, n, r), o === null && Bs(e, t, r, Aa, n), o === i) break;
          i = o;
        }
        i !== null && r.stopPropagation();
      } else Bs(e, t, r, null, n);
    }
  }
  var Aa = null;
  function Pl(e, t, n, r) {
    if (Aa = null, e = xu(r), e = xr(e), e !== null) if (t = Or(e), t === null) e = null;
    else if (n = t.tag, n === 13) {
      if (e = eh(t), e !== null) return e;
      e = null;
    } else if (n === 3) {
      if (t.stateNode.current.memoizedState.isDehydrated) return t.tag === 3 ? t.stateNode.containerInfo : null;
      e = null;
    } else t !== e && (e = null);
    return Aa = e, null;
  }
  function hh(e) {
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
        switch (rv()) {
          case Tu:
            return 1;
          case ih:
            return 4;
          case xa:
          case iv:
            return 16;
          case oh:
            return 536870912;
          default:
            return 16;
        }
      default:
        return 16;
    }
  }
  var or = null, Du = null, da = null;
  function ph() {
    if (da) return da;
    var e, t = Du, n = t.length, r, i = "value" in or ? or.value : or.textContent, o = i.length;
    for (e = 0; e < n && t[e] === i[e]; e++) ;
    var a = n - e;
    for (r = 1; r <= a && t[n - r] === i[o - r]; r++) ;
    return da = i.slice(e, 1 < r ? 1 - r : void 0);
  }
  function fa(e) {
    var t = e.keyCode;
    return "charCode" in e ? (e = e.charCode, e === 0 && t === 13 && (e = 13)) : e = t, e === 10 && (e = 13), 32 <= e || e === 13 ? e : 0;
  }
  function jo() {
    return true;
  }
  function Oc() {
    return false;
  }
  function Yt(e) {
    function t(n, r, i, o, a) {
      this._reactName = n, this._targetInst = i, this.type = r, this.nativeEvent = o, this.target = a, this.currentTarget = null;
      for (var s in e) e.hasOwnProperty(s) && (n = e[s], this[s] = n ? n(o) : o[s]);
      return this.isDefaultPrevented = (o.defaultPrevented != null ? o.defaultPrevented : o.returnValue === false) ? jo : Oc, this.isPropagationStopped = Oc, this;
    }
    return je(t.prototype, {
      preventDefault: function() {
        this.defaultPrevented = true;
        var n = this.nativeEvent;
        n && (n.preventDefault ? n.preventDefault() : typeof n.returnValue != "unknown" && (n.returnValue = false), this.isDefaultPrevented = jo);
      },
      stopPropagation: function() {
        var n = this.nativeEvent;
        n && (n.stopPropagation ? n.stopPropagation() : typeof n.cancelBubble != "unknown" && (n.cancelBubble = true), this.isPropagationStopped = jo);
      },
      persist: function() {
      },
      isPersistent: jo
    }), t;
  }
  var wi = {
    eventPhase: 0,
    bubbles: 0,
    cancelable: 0,
    timeStamp: function(e) {
      return e.timeStamp || Date.now();
    },
    defaultPrevented: 0,
    isTrusted: 0
  }, Pu = Yt(wi), Ao = je({}, wi, {
    view: 0,
    detail: 0
  }), vv = Yt(Ao), Ds, Ps, Pi, ts = je({}, Ao, {
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
    getModifierState: Iu,
    button: 0,
    buttons: 0,
    relatedTarget: function(e) {
      return e.relatedTarget === void 0 ? e.fromElement === e.srcElement ? e.toElement : e.fromElement : e.relatedTarget;
    },
    movementX: function(e) {
      return "movementX" in e ? e.movementX : (e !== Pi && (Pi && e.type === "mousemove" ? (Ds = e.screenX - Pi.screenX, Ps = e.screenY - Pi.screenY) : Ps = Ds = 0, Pi = e), Ds);
    },
    movementY: function(e) {
      return "movementY" in e ? e.movementY : Ps;
    }
  }), Gc = Yt(ts), yv = je({}, ts, {
    dataTransfer: 0
  }), wv = Yt(yv), Ev = je({}, Ao, {
    relatedTarget: 0
  }), Is = Yt(Ev), Sv = je({}, wi, {
    animationName: 0,
    elapsedTime: 0,
    pseudoElement: 0
  }), _v = Yt(Sv), kv = je({}, wi, {
    clipboardData: function(e) {
      return "clipboardData" in e ? e.clipboardData : window.clipboardData;
    }
  }), bv = Yt(kv), Cv = je({}, wi, {
    data: 0
  }), Uc = Yt(Cv), xv = {
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
  }, Tv = {
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
  }, Rv = {
    Alt: "altKey",
    Control: "ctrlKey",
    Meta: "metaKey",
    Shift: "shiftKey"
  };
  function Av(e) {
    var t = this.nativeEvent;
    return t.getModifierState ? t.getModifierState(e) : (e = Rv[e]) ? !!t[e] : false;
  }
  function Iu() {
    return Av;
  }
  var Lv = je({}, Ao, {
    key: function(e) {
      if (e.key) {
        var t = xv[e.key] || e.key;
        if (t !== "Unidentified") return t;
      }
      return e.type === "keypress" ? (e = fa(e), e === 13 ? "Enter" : String.fromCharCode(e)) : e.type === "keydown" || e.type === "keyup" ? Tv[e.keyCode] || "Unidentified" : "";
    },
    code: 0,
    location: 0,
    ctrlKey: 0,
    shiftKey: 0,
    altKey: 0,
    metaKey: 0,
    repeat: 0,
    locale: 0,
    getModifierState: Iu,
    charCode: function(e) {
      return e.type === "keypress" ? fa(e) : 0;
    },
    keyCode: function(e) {
      return e.type === "keydown" || e.type === "keyup" ? e.keyCode : 0;
    },
    which: function(e) {
      return e.type === "keypress" ? fa(e) : e.type === "keydown" || e.type === "keyup" ? e.keyCode : 0;
    }
  }), Dv = Yt(Lv), Pv = je({}, ts, {
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
  }), Bc = Yt(Pv), Iv = je({}, Ao, {
    touches: 0,
    targetTouches: 0,
    changedTouches: 0,
    altKey: 0,
    metaKey: 0,
    ctrlKey: 0,
    shiftKey: 0,
    getModifierState: Iu
  }), Fv = Yt(Iv), Nv = je({}, wi, {
    propertyName: 0,
    elapsedTime: 0,
    pseudoElement: 0
  }), zv = Yt(Nv), Ov = je({}, ts, {
    deltaX: function(e) {
      return "deltaX" in e ? e.deltaX : "wheelDeltaX" in e ? -e.wheelDeltaX : 0;
    },
    deltaY: function(e) {
      return "deltaY" in e ? e.deltaY : "wheelDeltaY" in e ? -e.wheelDeltaY : "wheelDelta" in e ? -e.wheelDelta : 0;
    },
    deltaZ: 0,
    deltaMode: 0
  }), Gv = Yt(Ov), Uv = [
    9,
    13,
    27,
    32
  ], Fu = jn && "CompositionEvent" in window, Ji = null;
  jn && "documentMode" in document && (Ji = document.documentMode);
  var Bv = jn && "TextEvent" in window && !Ji, gh = jn && (!Fu || Ji && 8 < Ji && 11 >= Ji), Mc = " ", $c = false;
  function mh(e, t) {
    switch (e) {
      case "keyup":
        return Uv.indexOf(t.keyCode) !== -1;
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
  function vh(e) {
    return e = e.detail, typeof e == "object" && "data" in e ? e.data : null;
  }
  var Hr = false;
  function Mv(e, t) {
    switch (e) {
      case "compositionend":
        return vh(t);
      case "keypress":
        return t.which !== 32 ? null : ($c = true, Mc);
      case "textInput":
        return e = t.data, e === Mc && $c ? null : e;
      default:
        return null;
    }
  }
  function $v(e, t) {
    if (Hr) return e === "compositionend" || !Fu && mh(e, t) ? (e = ph(), da = Du = or = null, Hr = false, e) : null;
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
        return gh && t.locale !== "ko" ? null : t.data;
      default:
        return null;
    }
  }
  var jv = {
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
  function jc(e) {
    var t = e && e.nodeName && e.nodeName.toLowerCase();
    return t === "input" ? !!jv[e.type] : t === "textarea";
  }
  function yh(e, t, n, r) {
    Qf(r), t = La(t, "onChange"), 0 < t.length && (n = new Pu("onChange", "change", null, n, r), e.push({
      event: n,
      listeners: t
    }));
  }
  var eo = null, po = null;
  function Hv(e) {
    Ah(e, 0);
  }
  function ns(e) {
    var t = Kr(e);
    if ($f(t)) return e;
  }
  function Wv(e, t) {
    if (e === "change") return t;
  }
  var wh = false;
  if (jn) {
    var Fs;
    if (jn) {
      var Ns = "oninput" in document;
      if (!Ns) {
        var Hc = document.createElement("div");
        Hc.setAttribute("oninput", "return;"), Ns = typeof Hc.oninput == "function";
      }
      Fs = Ns;
    } else Fs = false;
    wh = Fs && (!document.documentMode || 9 < document.documentMode);
  }
  function Wc() {
    eo && (eo.detachEvent("onpropertychange", Eh), po = eo = null);
  }
  function Eh(e) {
    if (e.propertyName === "value" && ns(po)) {
      var t = [];
      yh(t, po, e, xu(e)), Jf(Hv, t);
    }
  }
  function Vv(e, t, n) {
    e === "focusin" ? (Wc(), eo = t, po = n, eo.attachEvent("onpropertychange", Eh)) : e === "focusout" && Wc();
  }
  function Kv(e) {
    if (e === "selectionchange" || e === "keyup" || e === "keydown") return ns(po);
  }
  function Yv(e, t) {
    if (e === "click") return ns(t);
  }
  function Qv(e, t) {
    if (e === "input" || e === "change") return ns(t);
  }
  function Xv(e, t) {
    return e === t && (e !== 0 || 1 / e === 1 / t) || e !== e && t !== t;
  }
  var Sn = typeof Object.is == "function" ? Object.is : Xv;
  function go(e, t) {
    if (Sn(e, t)) return true;
    if (typeof e != "object" || e === null || typeof t != "object" || t === null) return false;
    var n = Object.keys(e), r = Object.keys(t);
    if (n.length !== r.length) return false;
    for (r = 0; r < n.length; r++) {
      var i = n[r];
      if (!pl.call(t, i) || !Sn(e[i], t[i])) return false;
    }
    return true;
  }
  function Vc(e) {
    for (; e && e.firstChild; ) e = e.firstChild;
    return e;
  }
  function Kc(e, t) {
    var n = Vc(e);
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
      n = Vc(n);
    }
  }
  function Sh(e, t) {
    return e && t ? e === t ? true : e && e.nodeType === 3 ? false : t && t.nodeType === 3 ? Sh(e, t.parentNode) : "contains" in e ? e.contains(t) : e.compareDocumentPosition ? !!(e.compareDocumentPosition(t) & 16) : false : false;
  }
  function _h() {
    for (var e = window, t = ka(); t instanceof e.HTMLIFrameElement; ) {
      try {
        var n = typeof t.contentWindow.location.href == "string";
      } catch {
        n = false;
      }
      if (n) e = t.contentWindow;
      else break;
      t = ka(e.document);
    }
    return t;
  }
  function Nu(e) {
    var t = e && e.nodeName && e.nodeName.toLowerCase();
    return t && (t === "input" && (e.type === "text" || e.type === "search" || e.type === "tel" || e.type === "url" || e.type === "password") || t === "textarea" || e.contentEditable === "true");
  }
  function Zv(e) {
    var t = _h(), n = e.focusedElem, r = e.selectionRange;
    if (t !== n && n && n.ownerDocument && Sh(n.ownerDocument.documentElement, n)) {
      if (r !== null && Nu(n)) {
        if (t = r.start, e = r.end, e === void 0 && (e = t), "selectionStart" in n) n.selectionStart = t, n.selectionEnd = Math.min(e, n.value.length);
        else if (e = (t = n.ownerDocument || document) && t.defaultView || window, e.getSelection) {
          e = e.getSelection();
          var i = n.textContent.length, o = Math.min(r.start, i);
          r = r.end === void 0 ? o : Math.min(r.end, i), !e.extend && o > r && (i = r, r = o, o = i), i = Kc(n, o);
          var a = Kc(n, r);
          i && a && (e.rangeCount !== 1 || e.anchorNode !== i.node || e.anchorOffset !== i.offset || e.focusNode !== a.node || e.focusOffset !== a.offset) && (t = t.createRange(), t.setStart(i.node, i.offset), e.removeAllRanges(), o > r ? (e.addRange(t), e.extend(a.node, a.offset)) : (t.setEnd(a.node, a.offset), e.addRange(t)));
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
  var qv = jn && "documentMode" in document && 11 >= document.documentMode, Wr = null, Il = null, to = null, Fl = false;
  function Yc(e, t, n) {
    var r = n.window === n ? n.document : n.nodeType === 9 ? n : n.ownerDocument;
    Fl || Wr == null || Wr !== ka(r) || (r = Wr, "selectionStart" in r && Nu(r) ? r = {
      start: r.selectionStart,
      end: r.selectionEnd
    } : (r = (r.ownerDocument && r.ownerDocument.defaultView || window).getSelection(), r = {
      anchorNode: r.anchorNode,
      anchorOffset: r.anchorOffset,
      focusNode: r.focusNode,
      focusOffset: r.focusOffset
    }), to && go(to, r) || (to = r, r = La(Il, "onSelect"), 0 < r.length && (t = new Pu("onSelect", "select", null, t, n), e.push({
      event: t,
      listeners: r
    }), t.target = Wr)));
  }
  function Ho(e, t) {
    var n = {};
    return n[e.toLowerCase()] = t.toLowerCase(), n["Webkit" + e] = "webkit" + t, n["Moz" + e] = "moz" + t, n;
  }
  var Vr = {
    animationend: Ho("Animation", "AnimationEnd"),
    animationiteration: Ho("Animation", "AnimationIteration"),
    animationstart: Ho("Animation", "AnimationStart"),
    transitionend: Ho("Transition", "TransitionEnd")
  }, zs = {}, kh = {};
  jn && (kh = document.createElement("div").style, "AnimationEvent" in window || (delete Vr.animationend.animation, delete Vr.animationiteration.animation, delete Vr.animationstart.animation), "TransitionEvent" in window || delete Vr.transitionend.transition);
  function rs(e) {
    if (zs[e]) return zs[e];
    if (!Vr[e]) return e;
    var t = Vr[e], n;
    for (n in t) if (t.hasOwnProperty(n) && n in kh) return zs[e] = t[n];
    return e;
  }
  var bh = rs("animationend"), Ch = rs("animationiteration"), xh = rs("animationstart"), Th = rs("transitionend"), Rh = /* @__PURE__ */ new Map(), Qc = "abort auxClick cancel canPlay canPlayThrough click close contextMenu copy cut drag dragEnd dragEnter dragExit dragLeave dragOver dragStart drop durationChange emptied encrypted ended error gotPointerCapture input invalid keyDown keyPress keyUp load loadedData loadedMetadata loadStart lostPointerCapture mouseDown mouseMove mouseOut mouseOver mouseUp paste pause play playing pointerCancel pointerDown pointerMove pointerOut pointerOver pointerUp progress rateChange reset resize seeked seeking stalled submit suspend timeUpdate touchCancel touchEnd touchStart volumeChange scroll toggle touchMove waiting wheel".split(" ");
  function vr(e, t) {
    Rh.set(e, t), zr(t, [
      e
    ]);
  }
  for (var Os = 0; Os < Qc.length; Os++) {
    var Gs = Qc[Os], Jv = Gs.toLowerCase(), ey = Gs[0].toUpperCase() + Gs.slice(1);
    vr(Jv, "on" + ey);
  }
  vr(bh, "onAnimationEnd");
  vr(Ch, "onAnimationIteration");
  vr(xh, "onAnimationStart");
  vr("dblclick", "onDoubleClick");
  vr("focusin", "onFocus");
  vr("focusout", "onBlur");
  vr(Th, "onTransitionEnd");
  li("onMouseEnter", [
    "mouseout",
    "mouseover"
  ]);
  li("onMouseLeave", [
    "mouseout",
    "mouseover"
  ]);
  li("onPointerEnter", [
    "pointerout",
    "pointerover"
  ]);
  li("onPointerLeave", [
    "pointerout",
    "pointerover"
  ]);
  zr("onChange", "change click focusin focusout input keydown keyup selectionchange".split(" "));
  zr("onSelect", "focusout contextmenu dragend focusin keydown keyup mousedown mouseup selectionchange".split(" "));
  zr("onBeforeInput", [
    "compositionend",
    "keypress",
    "textInput",
    "paste"
  ]);
  zr("onCompositionEnd", "compositionend focusout keydown keypress keyup mousedown".split(" "));
  zr("onCompositionStart", "compositionstart focusout keydown keypress keyup mousedown".split(" "));
  zr("onCompositionUpdate", "compositionupdate focusout keydown keypress keyup mousedown".split(" "));
  var Qi = "abort canplay canplaythrough durationchange emptied encrypted ended error loadeddata loadedmetadata loadstart pause play playing progress ratechange resize seeked seeking stalled suspend timeupdate volumechange waiting".split(" "), ty = new Set("cancel close invalid load scroll toggle".split(" ").concat(Qi));
  function Xc(e, t, n) {
    var r = e.type || "unknown-event";
    e.currentTarget = n, Jm(r, t, void 0, e), e.currentTarget = null;
  }
  function Ah(e, t) {
    t = (t & 4) !== 0;
    for (var n = 0; n < e.length; n++) {
      var r = e[n], i = r.event;
      r = r.listeners;
      e: {
        var o = void 0;
        if (t) for (var a = r.length - 1; 0 <= a; a--) {
          var s = r[a], l = s.instance, c = s.currentTarget;
          if (s = s.listener, l !== o && i.isPropagationStopped()) break e;
          Xc(i, s, c), o = l;
        }
        else for (a = 0; a < r.length; a++) {
          if (s = r[a], l = s.instance, c = s.currentTarget, s = s.listener, l !== o && i.isPropagationStopped()) break e;
          Xc(i, s, c), o = l;
        }
      }
    }
    if (Ca) throw e = Al, Ca = false, Al = null, e;
  }
  function Oe(e, t) {
    var n = t[Ul];
    n === void 0 && (n = t[Ul] = /* @__PURE__ */ new Set());
    var r = e + "__bubble";
    n.has(r) || (Lh(t, e, 2, false), n.add(r));
  }
  function Us(e, t, n) {
    var r = 0;
    t && (r |= 4), Lh(n, e, r, t);
  }
  var Wo = "_reactListening" + Math.random().toString(36).slice(2);
  function mo(e) {
    if (!e[Wo]) {
      e[Wo] = true, Of.forEach(function(n) {
        n !== "selectionchange" && (ty.has(n) || Us(n, false, e), Us(n, true, e));
      });
      var t = e.nodeType === 9 ? e : e.ownerDocument;
      t === null || t[Wo] || (t[Wo] = true, Us("selectionchange", false, t));
    }
  }
  function Lh(e, t, n, r) {
    switch (hh(t)) {
      case 1:
        var i = gv;
        break;
      case 4:
        i = mv;
        break;
      default:
        i = Lu;
    }
    n = i.bind(null, t, n, e), i = void 0, !Rl || t !== "touchstart" && t !== "touchmove" && t !== "wheel" || (i = true), r ? i !== void 0 ? e.addEventListener(t, n, {
      capture: true,
      passive: i
    }) : e.addEventListener(t, n, true) : i !== void 0 ? e.addEventListener(t, n, {
      passive: i
    }) : e.addEventListener(t, n, false);
  }
  function Bs(e, t, n, r, i) {
    var o = r;
    if (!(t & 1) && !(t & 2) && r !== null) e: for (; ; ) {
      if (r === null) return;
      var a = r.tag;
      if (a === 3 || a === 4) {
        var s = r.stateNode.containerInfo;
        if (s === i || s.nodeType === 8 && s.parentNode === i) break;
        if (a === 4) for (a = r.return; a !== null; ) {
          var l = a.tag;
          if ((l === 3 || l === 4) && (l = a.stateNode.containerInfo, l === i || l.nodeType === 8 && l.parentNode === i)) return;
          a = a.return;
        }
        for (; s !== null; ) {
          if (a = xr(s), a === null) return;
          if (l = a.tag, l === 5 || l === 6) {
            r = o = a;
            continue e;
          }
          s = s.parentNode;
        }
      }
      r = r.return;
    }
    Jf(function() {
      var c = o, h = xu(n), f = [];
      e: {
        var p = Rh.get(e);
        if (p !== void 0) {
          var y = Pu, k = e;
          switch (e) {
            case "keypress":
              if (fa(n) === 0) break e;
            case "keydown":
            case "keyup":
              y = Dv;
              break;
            case "focusin":
              k = "focus", y = Is;
              break;
            case "focusout":
              k = "blur", y = Is;
              break;
            case "beforeblur":
            case "afterblur":
              y = Is;
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
              y = Gc;
              break;
            case "drag":
            case "dragend":
            case "dragenter":
            case "dragexit":
            case "dragleave":
            case "dragover":
            case "dragstart":
            case "drop":
              y = wv;
              break;
            case "touchcancel":
            case "touchend":
            case "touchmove":
            case "touchstart":
              y = Fv;
              break;
            case bh:
            case Ch:
            case xh:
              y = _v;
              break;
            case Th:
              y = zv;
              break;
            case "scroll":
              y = vv;
              break;
            case "wheel":
              y = Gv;
              break;
            case "copy":
            case "cut":
            case "paste":
              y = bv;
              break;
            case "gotpointercapture":
            case "lostpointercapture":
            case "pointercancel":
            case "pointerdown":
            case "pointermove":
            case "pointerout":
            case "pointerover":
            case "pointerup":
              y = Bc;
          }
          var b = (t & 4) !== 0, I = !b && e === "scroll", S = b ? p !== null ? p + "Capture" : null : p;
          b = [];
          for (var m = c, v; m !== null; ) {
            v = m;
            var E = v.stateNode;
            if (v.tag === 5 && E !== null && (v = E, S !== null && (E = uo(m, S), E != null && b.push(vo(m, E, v)))), I) break;
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
          if (p = e === "mouseover" || e === "pointerover", y = e === "mouseout" || e === "pointerout", p && n !== xl && (k = n.relatedTarget || n.fromElement) && (xr(k) || k[Hn])) break e;
          if ((y || p) && (p = h.window === h ? h : (p = h.ownerDocument) ? p.defaultView || p.parentWindow : window, y ? (k = n.relatedTarget || n.toElement, y = c, k = k ? xr(k) : null, k !== null && (I = Or(k), k !== I || k.tag !== 5 && k.tag !== 6) && (k = null)) : (y = null, k = c), y !== k)) {
            if (b = Gc, E = "onMouseLeave", S = "onMouseEnter", m = "mouse", (e === "pointerout" || e === "pointerover") && (b = Bc, E = "onPointerLeave", S = "onPointerEnter", m = "pointer"), I = y == null ? p : Kr(y), v = k == null ? p : Kr(k), p = new b(E, m + "leave", y, n, h), p.target = I, p.relatedTarget = v, E = null, xr(h) === c && (b = new b(S, m + "enter", k, n, h), b.target = v, b.relatedTarget = I, E = b), I = E, y && k) t: {
              for (b = y, S = k, m = 0, v = b; v; v = Gr(v)) m++;
              for (v = 0, E = S; E; E = Gr(E)) v++;
              for (; 0 < m - v; ) b = Gr(b), m--;
              for (; 0 < v - m; ) S = Gr(S), v--;
              for (; m--; ) {
                if (b === S || S !== null && b === S.alternate) break t;
                b = Gr(b), S = Gr(S);
              }
              b = null;
            }
            else b = null;
            y !== null && Zc(f, p, y, b, false), k !== null && I !== null && Zc(f, I, k, b, true);
          }
        }
        e: {
          if (p = c ? Kr(c) : window, y = p.nodeName && p.nodeName.toLowerCase(), y === "select" || y === "input" && p.type === "file") var A = Wv;
          else if (jc(p)) if (wh) A = Qv;
          else {
            A = Kv;
            var F = Vv;
          }
          else (y = p.nodeName) && y.toLowerCase() === "input" && (p.type === "checkbox" || p.type === "radio") && (A = Yv);
          if (A && (A = A(e, c))) {
            yh(f, A, n, h);
            break e;
          }
          F && F(e, p, c), e === "focusout" && (F = p._wrapperState) && F.controlled && p.type === "number" && Sl(p, "number", p.value);
        }
        switch (F = c ? Kr(c) : window, e) {
          case "focusin":
            (jc(F) || F.contentEditable === "true") && (Wr = F, Il = c, to = null);
            break;
          case "focusout":
            to = Il = Wr = null;
            break;
          case "mousedown":
            Fl = true;
            break;
          case "contextmenu":
          case "mouseup":
          case "dragend":
            Fl = false, Yc(f, n, h);
            break;
          case "selectionchange":
            if (qv) break;
          case "keydown":
          case "keyup":
            Yc(f, n, h);
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
        else Hr ? mh(e, n) && (L = "onCompositionEnd") : e === "keydown" && n.keyCode === 229 && (L = "onCompositionStart");
        L && (gh && n.locale !== "ko" && (Hr || L !== "onCompositionStart" ? L === "onCompositionEnd" && Hr && (R = ph()) : (or = h, Du = "value" in or ? or.value : or.textContent, Hr = true)), F = La(c, L), 0 < F.length && (L = new Uc(L, e, null, n, h), f.push({
          event: L,
          listeners: F
        }), R ? L.data = R : (R = vh(n), R !== null && (L.data = R)))), (R = Bv ? Mv(e, n) : $v(e, n)) && (c = La(c, "onBeforeInput"), 0 < c.length && (h = new Uc("onBeforeInput", "beforeinput", null, n, h), f.push({
          event: h,
          listeners: c
        }), h.data = R));
      }
      Ah(f, t);
    });
  }
  function vo(e, t, n) {
    return {
      instance: e,
      listener: t,
      currentTarget: n
    };
  }
  function La(e, t) {
    for (var n = t + "Capture", r = []; e !== null; ) {
      var i = e, o = i.stateNode;
      i.tag === 5 && o !== null && (i = o, o = uo(e, n), o != null && r.unshift(vo(e, o, i)), o = uo(e, t), o != null && r.push(vo(e, o, i))), e = e.return;
    }
    return r;
  }
  function Gr(e) {
    if (e === null) return null;
    do
      e = e.return;
    while (e && e.tag !== 5);
    return e || null;
  }
  function Zc(e, t, n, r, i) {
    for (var o = t._reactName, a = []; n !== null && n !== r; ) {
      var s = n, l = s.alternate, c = s.stateNode;
      if (l !== null && l === r) break;
      s.tag === 5 && c !== null && (s = c, i ? (l = uo(n, o), l != null && a.unshift(vo(n, l, s))) : i || (l = uo(n, o), l != null && a.push(vo(n, l, s)))), n = n.return;
    }
    a.length !== 0 && e.push({
      event: t,
      listeners: a
    });
  }
  var ny = /\r\n?/g, ry = /\u0000|\uFFFD/g;
  function qc(e) {
    return (typeof e == "string" ? e : "" + e).replace(ny, `
`).replace(ry, "");
  }
  function Vo(e, t, n) {
    if (t = qc(t), qc(e) !== t && n) throw Error(j(425));
  }
  function Da() {
  }
  var Nl = null, zl = null;
  function Ol(e, t) {
    return e === "textarea" || e === "noscript" || typeof t.children == "string" || typeof t.children == "number" || typeof t.dangerouslySetInnerHTML == "object" && t.dangerouslySetInnerHTML !== null && t.dangerouslySetInnerHTML.__html != null;
  }
  var Gl = typeof setTimeout == "function" ? setTimeout : void 0, iy = typeof clearTimeout == "function" ? clearTimeout : void 0, Jc = typeof Promise == "function" ? Promise : void 0, oy = typeof queueMicrotask == "function" ? queueMicrotask : typeof Jc < "u" ? function(e) {
    return Jc.resolve(null).then(e).catch(ay);
  } : Gl;
  function ay(e) {
    setTimeout(function() {
      throw e;
    });
  }
  function Ms(e, t) {
    var n = t, r = 0;
    do {
      var i = n.nextSibling;
      if (e.removeChild(n), i && i.nodeType === 8) if (n = i.data, n === "/$") {
        if (r === 0) {
          e.removeChild(i), ho(t);
          return;
        }
        r--;
      } else n !== "$" && n !== "$?" && n !== "$!" || r++;
      n = i;
    } while (n);
    ho(t);
  }
  function cr(e) {
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
  function ed(e) {
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
  var Ei = Math.random().toString(36).slice(2), Tn = "__reactFiber$" + Ei, yo = "__reactProps$" + Ei, Hn = "__reactContainer$" + Ei, Ul = "__reactEvents$" + Ei, sy = "__reactListeners$" + Ei, ly = "__reactHandles$" + Ei;
  function xr(e) {
    var t = e[Tn];
    if (t) return t;
    for (var n = e.parentNode; n; ) {
      if (t = n[Hn] || n[Tn]) {
        if (n = t.alternate, t.child !== null || n !== null && n.child !== null) for (e = ed(e); e !== null; ) {
          if (n = e[Tn]) return n;
          e = ed(e);
        }
        return t;
      }
      e = n, n = e.parentNode;
    }
    return null;
  }
  function Lo(e) {
    return e = e[Tn] || e[Hn], !e || e.tag !== 5 && e.tag !== 6 && e.tag !== 13 && e.tag !== 3 ? null : e;
  }
  function Kr(e) {
    if (e.tag === 5 || e.tag === 6) return e.stateNode;
    throw Error(j(33));
  }
  function is(e) {
    return e[yo] || null;
  }
  var Bl = [], Yr = -1;
  function yr(e) {
    return {
      current: e
    };
  }
  function Ge(e) {
    0 > Yr || (e.current = Bl[Yr], Bl[Yr] = null, Yr--);
  }
  function Ne(e, t) {
    Yr++, Bl[Yr] = e.current, e.current = t;
  }
  var mr = {}, Ct = yr(mr), Ut = yr(false), Dr = mr;
  function ui(e, t) {
    var n = e.type.contextTypes;
    if (!n) return mr;
    var r = e.stateNode;
    if (r && r.__reactInternalMemoizedUnmaskedChildContext === t) return r.__reactInternalMemoizedMaskedChildContext;
    var i = {}, o;
    for (o in n) i[o] = t[o];
    return r && (e = e.stateNode, e.__reactInternalMemoizedUnmaskedChildContext = t, e.__reactInternalMemoizedMaskedChildContext = i), i;
  }
  function Bt(e) {
    return e = e.childContextTypes, e != null;
  }
  function Pa() {
    Ge(Ut), Ge(Ct);
  }
  function td(e, t, n) {
    if (Ct.current !== mr) throw Error(j(168));
    Ne(Ct, t), Ne(Ut, n);
  }
  function Dh(e, t, n) {
    var r = e.stateNode;
    if (t = t.childContextTypes, typeof r.getChildContext != "function") return n;
    r = r.getChildContext();
    for (var i in r) if (!(i in t)) throw Error(j(108, Vm(e) || "Unknown", i));
    return je({}, n, r);
  }
  function Ia(e) {
    return e = (e = e.stateNode) && e.__reactInternalMemoizedMergedChildContext || mr, Dr = Ct.current, Ne(Ct, e), Ne(Ut, Ut.current), true;
  }
  function nd(e, t, n) {
    var r = e.stateNode;
    if (!r) throw Error(j(169));
    n ? (e = Dh(e, t, Dr), r.__reactInternalMemoizedMergedChildContext = e, Ge(Ut), Ge(Ct), Ne(Ct, e)) : Ge(Ut), Ne(Ut, n);
  }
  var On = null, os = false, $s = false;
  function Ph(e) {
    On === null ? On = [
      e
    ] : On.push(e);
  }
  function uy(e) {
    os = true, Ph(e);
  }
  function wr() {
    if (!$s && On !== null) {
      $s = true;
      var e = 0, t = Pe;
      try {
        var n = On;
        for (Pe = 1; e < n.length; e++) {
          var r = n[e];
          do
            r = r(true);
          while (r !== null);
        }
        On = null, os = false;
      } catch (i) {
        throw On !== null && (On = On.slice(e + 1)), rh(Tu, wr), i;
      } finally {
        Pe = t, $s = false;
      }
    }
    return null;
  }
  var Qr = [], Xr = 0, Fa = null, Na = 0, qt = [], Jt = 0, Pr = null, Un = 1, Bn = "";
  function kr(e, t) {
    Qr[Xr++] = Na, Qr[Xr++] = Fa, Fa = e, Na = t;
  }
  function Ih(e, t, n) {
    qt[Jt++] = Un, qt[Jt++] = Bn, qt[Jt++] = Pr, Pr = e;
    var r = Un;
    e = Bn;
    var i = 32 - wn(r) - 1;
    r &= ~(1 << i), n += 1;
    var o = 32 - wn(t) + i;
    if (30 < o) {
      var a = i - i % 5;
      o = (r & (1 << a) - 1).toString(32), r >>= a, i -= a, Un = 1 << 32 - wn(t) + i | n << i | r, Bn = o + e;
    } else Un = 1 << o | n << i | r, Bn = e;
  }
  function zu(e) {
    e.return !== null && (kr(e, 1), Ih(e, 1, 0));
  }
  function Ou(e) {
    for (; e === Fa; ) Fa = Qr[--Xr], Qr[Xr] = null, Na = Qr[--Xr], Qr[Xr] = null;
    for (; e === Pr; ) Pr = qt[--Jt], qt[Jt] = null, Bn = qt[--Jt], qt[Jt] = null, Un = qt[--Jt], qt[Jt] = null;
  }
  var Wt = null, Ht = null, Ue = false, vn = null;
  function Fh(e, t) {
    var n = en(5, null, null, 0);
    n.elementType = "DELETED", n.stateNode = t, n.return = e, t = e.deletions, t === null ? (e.deletions = [
      n
    ], e.flags |= 16) : t.push(n);
  }
  function rd(e, t) {
    switch (e.tag) {
      case 5:
        var n = e.type;
        return t = t.nodeType !== 1 || n.toLowerCase() !== t.nodeName.toLowerCase() ? null : t, t !== null ? (e.stateNode = t, Wt = e, Ht = cr(t.firstChild), true) : false;
      case 6:
        return t = e.pendingProps === "" || t.nodeType !== 3 ? null : t, t !== null ? (e.stateNode = t, Wt = e, Ht = null, true) : false;
      case 13:
        return t = t.nodeType !== 8 ? null : t, t !== null ? (n = Pr !== null ? {
          id: Un,
          overflow: Bn
        } : null, e.memoizedState = {
          dehydrated: t,
          treeContext: n,
          retryLane: 1073741824
        }, n = en(18, null, null, 0), n.stateNode = t, n.return = e, e.child = n, Wt = e, Ht = null, true) : false;
      default:
        return false;
    }
  }
  function Ml(e) {
    return (e.mode & 1) !== 0 && (e.flags & 128) === 0;
  }
  function $l(e) {
    if (Ue) {
      var t = Ht;
      if (t) {
        var n = t;
        if (!rd(e, t)) {
          if (Ml(e)) throw Error(j(418));
          t = cr(n.nextSibling);
          var r = Wt;
          t && rd(e, t) ? Fh(r, n) : (e.flags = e.flags & -4097 | 2, Ue = false, Wt = e);
        }
      } else {
        if (Ml(e)) throw Error(j(418));
        e.flags = e.flags & -4097 | 2, Ue = false, Wt = e;
      }
    }
  }
  function id(e) {
    for (e = e.return; e !== null && e.tag !== 5 && e.tag !== 3 && e.tag !== 13; ) e = e.return;
    Wt = e;
  }
  function Ko(e) {
    if (e !== Wt) return false;
    if (!Ue) return id(e), Ue = true, false;
    var t;
    if ((t = e.tag !== 3) && !(t = e.tag !== 5) && (t = e.type, t = t !== "head" && t !== "body" && !Ol(e.type, e.memoizedProps)), t && (t = Ht)) {
      if (Ml(e)) throw Nh(), Error(j(418));
      for (; t; ) Fh(e, t), t = cr(t.nextSibling);
    }
    if (id(e), e.tag === 13) {
      if (e = e.memoizedState, e = e !== null ? e.dehydrated : null, !e) throw Error(j(317));
      e: {
        for (e = e.nextSibling, t = 0; e; ) {
          if (e.nodeType === 8) {
            var n = e.data;
            if (n === "/$") {
              if (t === 0) {
                Ht = cr(e.nextSibling);
                break e;
              }
              t--;
            } else n !== "$" && n !== "$!" && n !== "$?" || t++;
          }
          e = e.nextSibling;
        }
        Ht = null;
      }
    } else Ht = Wt ? cr(e.stateNode.nextSibling) : null;
    return true;
  }
  function Nh() {
    for (var e = Ht; e; ) e = cr(e.nextSibling);
  }
  function ci() {
    Ht = Wt = null, Ue = false;
  }
  function Gu(e) {
    vn === null ? vn = [
      e
    ] : vn.push(e);
  }
  var cy = Kn.ReactCurrentBatchConfig;
  function Ii(e, t, n) {
    if (e = n.ref, e !== null && typeof e != "function" && typeof e != "object") {
      if (n._owner) {
        if (n = n._owner, n) {
          if (n.tag !== 1) throw Error(j(309));
          var r = n.stateNode;
        }
        if (!r) throw Error(j(147, e));
        var i = r, o = "" + e;
        return t !== null && t.ref !== null && typeof t.ref == "function" && t.ref._stringRef === o ? t.ref : (t = function(a) {
          var s = i.refs;
          a === null ? delete s[o] : s[o] = a;
        }, t._stringRef = o, t);
      }
      if (typeof e != "string") throw Error(j(284));
      if (!n._owner) throw Error(j(290, e));
    }
    return e;
  }
  function Yo(e, t) {
    throw e = Object.prototype.toString.call(t), Error(j(31, e === "[object Object]" ? "object with keys {" + Object.keys(t).join(", ") + "}" : e));
  }
  function od(e) {
    var t = e._init;
    return t(e._payload);
  }
  function zh(e) {
    function t(S, m) {
      if (e) {
        var v = S.deletions;
        v === null ? (S.deletions = [
          m
        ], S.flags |= 16) : v.push(m);
      }
    }
    function n(S, m) {
      if (!e) return null;
      for (; m !== null; ) t(S, m), m = m.sibling;
      return null;
    }
    function r(S, m) {
      for (S = /* @__PURE__ */ new Map(); m !== null; ) m.key !== null ? S.set(m.key, m) : S.set(m.index, m), m = m.sibling;
      return S;
    }
    function i(S, m) {
      return S = pr(S, m), S.index = 0, S.sibling = null, S;
    }
    function o(S, m, v) {
      return S.index = v, e ? (v = S.alternate, v !== null ? (v = v.index, v < m ? (S.flags |= 2, m) : v) : (S.flags |= 2, m)) : (S.flags |= 1048576, m);
    }
    function a(S) {
      return e && S.alternate === null && (S.flags |= 2), S;
    }
    function s(S, m, v, E) {
      return m === null || m.tag !== 6 ? (m = Qs(v, S.mode, E), m.return = S, m) : (m = i(m, v), m.return = S, m);
    }
    function l(S, m, v, E) {
      var A = v.type;
      return A === jr ? h(S, m, v.props.children, E, v.key) : m !== null && (m.elementType === A || typeof A == "object" && A !== null && A.$$typeof === tr && od(A) === m.type) ? (E = i(m, v.props), E.ref = Ii(S, m, v), E.return = S, E) : (E = wa(v.type, v.key, v.props, null, S.mode, E), E.ref = Ii(S, m, v), E.return = S, E);
    }
    function c(S, m, v, E) {
      return m === null || m.tag !== 4 || m.stateNode.containerInfo !== v.containerInfo || m.stateNode.implementation !== v.implementation ? (m = Xs(v, S.mode, E), m.return = S, m) : (m = i(m, v.children || []), m.return = S, m);
    }
    function h(S, m, v, E, A) {
      return m === null || m.tag !== 7 ? (m = Lr(v, S.mode, E, A), m.return = S, m) : (m = i(m, v), m.return = S, m);
    }
    function f(S, m, v) {
      if (typeof m == "string" && m !== "" || typeof m == "number") return m = Qs("" + m, S.mode, v), m.return = S, m;
      if (typeof m == "object" && m !== null) {
        switch (m.$$typeof) {
          case Oo:
            return v = wa(m.type, m.key, m.props, null, S.mode, v), v.ref = Ii(S, null, m), v.return = S, v;
          case $r:
            return m = Xs(m, S.mode, v), m.return = S, m;
          case tr:
            var E = m._init;
            return f(S, E(m._payload), v);
        }
        if (Ki(m) || Ri(m)) return m = Lr(m, S.mode, v, null), m.return = S, m;
        Yo(S, m);
      }
      return null;
    }
    function p(S, m, v, E) {
      var A = m !== null ? m.key : null;
      if (typeof v == "string" && v !== "" || typeof v == "number") return A !== null ? null : s(S, m, "" + v, E);
      if (typeof v == "object" && v !== null) {
        switch (v.$$typeof) {
          case Oo:
            return v.key === A ? l(S, m, v, E) : null;
          case $r:
            return v.key === A ? c(S, m, v, E) : null;
          case tr:
            return A = v._init, p(S, m, A(v._payload), E);
        }
        if (Ki(v) || Ri(v)) return A !== null ? null : h(S, m, v, E, null);
        Yo(S, v);
      }
      return null;
    }
    function y(S, m, v, E, A) {
      if (typeof E == "string" && E !== "" || typeof E == "number") return S = S.get(v) || null, s(m, S, "" + E, A);
      if (typeof E == "object" && E !== null) {
        switch (E.$$typeof) {
          case Oo:
            return S = S.get(E.key === null ? v : E.key) || null, l(m, S, E, A);
          case $r:
            return S = S.get(E.key === null ? v : E.key) || null, c(m, S, E, A);
          case tr:
            var F = E._init;
            return y(S, m, v, F(E._payload), A);
        }
        if (Ki(E) || Ri(E)) return S = S.get(v) || null, h(m, S, E, A, null);
        Yo(m, E);
      }
      return null;
    }
    function k(S, m, v, E) {
      for (var A = null, F = null, R = m, L = m = 0, x = null; R !== null && L < v.length; L++) {
        R.index > L ? (x = R, R = null) : x = R.sibling;
        var G = p(S, R, v[L], E);
        if (G === null) {
          R === null && (R = x);
          break;
        }
        e && R && G.alternate === null && t(S, R), m = o(G, m, L), F === null ? A = G : F.sibling = G, F = G, R = x;
      }
      if (L === v.length) return n(S, R), Ue && kr(S, L), A;
      if (R === null) {
        for (; L < v.length; L++) R = f(S, v[L], E), R !== null && (m = o(R, m, L), F === null ? A = R : F.sibling = R, F = R);
        return Ue && kr(S, L), A;
      }
      for (R = r(S, R); L < v.length; L++) x = y(R, S, L, v[L], E), x !== null && (e && x.alternate !== null && R.delete(x.key === null ? L : x.key), m = o(x, m, L), F === null ? A = x : F.sibling = x, F = x);
      return e && R.forEach(function(V) {
        return t(S, V);
      }), Ue && kr(S, L), A;
    }
    function b(S, m, v, E) {
      var A = Ri(v);
      if (typeof A != "function") throw Error(j(150));
      if (v = A.call(v), v == null) throw Error(j(151));
      for (var F = A = null, R = m, L = m = 0, x = null, G = v.next(); R !== null && !G.done; L++, G = v.next()) {
        R.index > L ? (x = R, R = null) : x = R.sibling;
        var V = p(S, R, G.value, E);
        if (V === null) {
          R === null && (R = x);
          break;
        }
        e && R && V.alternate === null && t(S, R), m = o(V, m, L), F === null ? A = V : F.sibling = V, F = V, R = x;
      }
      if (G.done) return n(S, R), Ue && kr(S, L), A;
      if (R === null) {
        for (; !G.done; L++, G = v.next()) G = f(S, G.value, E), G !== null && (m = o(G, m, L), F === null ? A = G : F.sibling = G, F = G);
        return Ue && kr(S, L), A;
      }
      for (R = r(S, R); !G.done; L++, G = v.next()) G = y(R, S, L, G.value, E), G !== null && (e && G.alternate !== null && R.delete(G.key === null ? L : G.key), m = o(G, m, L), F === null ? A = G : F.sibling = G, F = G);
      return e && R.forEach(function(B) {
        return t(S, B);
      }), Ue && kr(S, L), A;
    }
    function I(S, m, v, E) {
      if (typeof v == "object" && v !== null && v.type === jr && v.key === null && (v = v.props.children), typeof v == "object" && v !== null) {
        switch (v.$$typeof) {
          case Oo:
            e: {
              for (var A = v.key, F = m; F !== null; ) {
                if (F.key === A) {
                  if (A = v.type, A === jr) {
                    if (F.tag === 7) {
                      n(S, F.sibling), m = i(F, v.props.children), m.return = S, S = m;
                      break e;
                    }
                  } else if (F.elementType === A || typeof A == "object" && A !== null && A.$$typeof === tr && od(A) === F.type) {
                    n(S, F.sibling), m = i(F, v.props), m.ref = Ii(S, F, v), m.return = S, S = m;
                    break e;
                  }
                  n(S, F);
                  break;
                } else t(S, F);
                F = F.sibling;
              }
              v.type === jr ? (m = Lr(v.props.children, S.mode, E, v.key), m.return = S, S = m) : (E = wa(v.type, v.key, v.props, null, S.mode, E), E.ref = Ii(S, m, v), E.return = S, S = E);
            }
            return a(S);
          case $r:
            e: {
              for (F = v.key; m !== null; ) {
                if (m.key === F) if (m.tag === 4 && m.stateNode.containerInfo === v.containerInfo && m.stateNode.implementation === v.implementation) {
                  n(S, m.sibling), m = i(m, v.children || []), m.return = S, S = m;
                  break e;
                } else {
                  n(S, m);
                  break;
                }
                else t(S, m);
                m = m.sibling;
              }
              m = Xs(v, S.mode, E), m.return = S, S = m;
            }
            return a(S);
          case tr:
            return F = v._init, I(S, m, F(v._payload), E);
        }
        if (Ki(v)) return k(S, m, v, E);
        if (Ri(v)) return b(S, m, v, E);
        Yo(S, v);
      }
      return typeof v == "string" && v !== "" || typeof v == "number" ? (v = "" + v, m !== null && m.tag === 6 ? (n(S, m.sibling), m = i(m, v), m.return = S, S = m) : (n(S, m), m = Qs(v, S.mode, E), m.return = S, S = m), a(S)) : n(S, m);
    }
    return I;
  }
  var di = zh(true), Oh = zh(false), za = yr(null), Oa = null, Zr = null, Uu = null;
  function Bu() {
    Uu = Zr = Oa = null;
  }
  function Mu(e) {
    var t = za.current;
    Ge(za), e._currentValue = t;
  }
  function jl(e, t, n) {
    for (; e !== null; ) {
      var r = e.alternate;
      if ((e.childLanes & t) !== t ? (e.childLanes |= t, r !== null && (r.childLanes |= t)) : r !== null && (r.childLanes & t) !== t && (r.childLanes |= t), e === n) break;
      e = e.return;
    }
  }
  function ii(e, t) {
    Oa = e, Uu = Zr = null, e = e.dependencies, e !== null && e.firstContext !== null && (e.lanes & t && (Gt = true), e.firstContext = null);
  }
  function rn(e) {
    var t = e._currentValue;
    if (Uu !== e) if (e = {
      context: e,
      memoizedValue: t,
      next: null
    }, Zr === null) {
      if (Oa === null) throw Error(j(308));
      Zr = e, Oa.dependencies = {
        lanes: 0,
        firstContext: e
      };
    } else Zr = Zr.next = e;
    return t;
  }
  var Tr = null;
  function $u(e) {
    Tr === null ? Tr = [
      e
    ] : Tr.push(e);
  }
  function Gh(e, t, n, r) {
    var i = t.interleaved;
    return i === null ? (n.next = n, $u(t)) : (n.next = i.next, i.next = n), t.interleaved = n, Wn(e, r);
  }
  function Wn(e, t) {
    e.lanes |= t;
    var n = e.alternate;
    for (n !== null && (n.lanes |= t), n = e, e = e.return; e !== null; ) e.childLanes |= t, n = e.alternate, n !== null && (n.childLanes |= t), n = e, e = e.return;
    return n.tag === 3 ? n.stateNode : null;
  }
  var nr = false;
  function ju(e) {
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
  function Uh(e, t) {
    e = e.updateQueue, t.updateQueue === e && (t.updateQueue = {
      baseState: e.baseState,
      firstBaseUpdate: e.firstBaseUpdate,
      lastBaseUpdate: e.lastBaseUpdate,
      shared: e.shared,
      effects: e.effects
    });
  }
  function Mn(e, t) {
    return {
      eventTime: e,
      lane: t,
      tag: 0,
      payload: null,
      callback: null,
      next: null
    };
  }
  function dr(e, t, n) {
    var r = e.updateQueue;
    if (r === null) return null;
    if (r = r.shared, be & 2) {
      var i = r.pending;
      return i === null ? t.next = t : (t.next = i.next, i.next = t), r.pending = t, Wn(e, n);
    }
    return i = r.interleaved, i === null ? (t.next = t, $u(r)) : (t.next = i.next, i.next = t), r.interleaved = t, Wn(e, n);
  }
  function ha(e, t, n) {
    if (t = t.updateQueue, t !== null && (t = t.shared, (n & 4194240) !== 0)) {
      var r = t.lanes;
      r &= e.pendingLanes, n |= r, t.lanes = n, Ru(e, n);
    }
  }
  function ad(e, t) {
    var n = e.updateQueue, r = e.alternate;
    if (r !== null && (r = r.updateQueue, n === r)) {
      var i = null, o = null;
      if (n = n.firstBaseUpdate, n !== null) {
        do {
          var a = {
            eventTime: n.eventTime,
            lane: n.lane,
            tag: n.tag,
            payload: n.payload,
            callback: n.callback,
            next: null
          };
          o === null ? i = o = a : o = o.next = a, n = n.next;
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
  function Ga(e, t, n, r) {
    var i = e.updateQueue;
    nr = false;
    var o = i.firstBaseUpdate, a = i.lastBaseUpdate, s = i.shared.pending;
    if (s !== null) {
      i.shared.pending = null;
      var l = s, c = l.next;
      l.next = null, a === null ? o = c : a.next = c, a = l;
      var h = e.alternate;
      h !== null && (h = h.updateQueue, s = h.lastBaseUpdate, s !== a && (s === null ? h.firstBaseUpdate = c : s.next = c, h.lastBaseUpdate = l));
    }
    if (o !== null) {
      var f = i.baseState;
      a = 0, h = c = l = null, s = o;
      do {
        var p = s.lane, y = s.eventTime;
        if ((r & p) === p) {
          h !== null && (h = h.next = {
            eventTime: y,
            lane: 0,
            tag: s.tag,
            payload: s.payload,
            callback: s.callback,
            next: null
          });
          e: {
            var k = e, b = s;
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
                nr = true;
            }
          }
          s.callback !== null && s.lane !== 0 && (e.flags |= 64, p = i.effects, p === null ? i.effects = [
            s
          ] : p.push(s));
        } else y = {
          eventTime: y,
          lane: p,
          tag: s.tag,
          payload: s.payload,
          callback: s.callback,
          next: null
        }, h === null ? (c = h = y, l = f) : h = h.next = y, a |= p;
        if (s = s.next, s === null) {
          if (s = i.shared.pending, s === null) break;
          p = s, s = p.next, p.next = null, i.lastBaseUpdate = p, i.shared.pending = null;
        }
      } while (true);
      if (h === null && (l = f), i.baseState = l, i.firstBaseUpdate = c, i.lastBaseUpdate = h, t = i.shared.interleaved, t !== null) {
        i = t;
        do
          a |= i.lane, i = i.next;
        while (i !== t);
      } else o === null && (i.shared.lanes = 0);
      Fr |= a, e.lanes = a, e.memoizedState = f;
    }
  }
  function sd(e, t, n) {
    if (e = t.effects, t.effects = null, e !== null) for (t = 0; t < e.length; t++) {
      var r = e[t], i = r.callback;
      if (i !== null) {
        if (r.callback = null, r = n, typeof i != "function") throw Error(j(191, i));
        i.call(r);
      }
    }
  }
  var Do = {}, Ln = yr(Do), wo = yr(Do), Eo = yr(Do);
  function Rr(e) {
    if (e === Do) throw Error(j(174));
    return e;
  }
  function Hu(e, t) {
    switch (Ne(Eo, t), Ne(wo, e), Ne(Ln, Do), e = t.nodeType, e) {
      case 9:
      case 11:
        t = (t = t.documentElement) ? t.namespaceURI : kl(null, "");
        break;
      default:
        e = e === 8 ? t.parentNode : t, t = e.namespaceURI || null, e = e.tagName, t = kl(t, e);
    }
    Ge(Ln), Ne(Ln, t);
  }
  function fi() {
    Ge(Ln), Ge(wo), Ge(Eo);
  }
  function Bh(e) {
    Rr(Eo.current);
    var t = Rr(Ln.current), n = kl(t, e.type);
    t !== n && (Ne(wo, e), Ne(Ln, n));
  }
  function Wu(e) {
    wo.current === e && (Ge(Ln), Ge(wo));
  }
  var Me = yr(0);
  function Ua(e) {
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
  var js = [];
  function Vu() {
    for (var e = 0; e < js.length; e++) js[e]._workInProgressVersionPrimary = null;
    js.length = 0;
  }
  var pa = Kn.ReactCurrentDispatcher, Hs = Kn.ReactCurrentBatchConfig, Ir = 0, $e = null, rt = null, ct = null, Ba = false, no = false, So = 0, dy = 0;
  function St() {
    throw Error(j(321));
  }
  function Ku(e, t) {
    if (t === null) return false;
    for (var n = 0; n < t.length && n < e.length; n++) if (!Sn(e[n], t[n])) return false;
    return true;
  }
  function Yu(e, t, n, r, i, o) {
    if (Ir = o, $e = t, t.memoizedState = null, t.updateQueue = null, t.lanes = 0, pa.current = e === null || e.memoizedState === null ? gy : my, e = n(r, i), no) {
      o = 0;
      do {
        if (no = false, So = 0, 25 <= o) throw Error(j(301));
        o += 1, ct = rt = null, t.updateQueue = null, pa.current = vy, e = n(r, i);
      } while (no);
    }
    if (pa.current = Ma, t = rt !== null && rt.next !== null, Ir = 0, ct = rt = $e = null, Ba = false, t) throw Error(j(300));
    return e;
  }
  function Qu() {
    var e = So !== 0;
    return So = 0, e;
  }
  function xn() {
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
      if (e === null) throw Error(j(310));
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
  function _o(e, t) {
    return typeof t == "function" ? t(e) : t;
  }
  function Ws(e) {
    var t = on(), n = t.queue;
    if (n === null) throw Error(j(311));
    n.lastRenderedReducer = e;
    var r = rt, i = r.baseQueue, o = n.pending;
    if (o !== null) {
      if (i !== null) {
        var a = i.next;
        i.next = o.next, o.next = a;
      }
      r.baseQueue = i = o, n.pending = null;
    }
    if (i !== null) {
      o = i.next, r = r.baseState;
      var s = a = null, l = null, c = o;
      do {
        var h = c.lane;
        if ((Ir & h) === h) l !== null && (l = l.next = {
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
          l === null ? (s = l = f, a = r) : l = l.next = f, $e.lanes |= h, Fr |= h;
        }
        c = c.next;
      } while (c !== null && c !== o);
      l === null ? a = r : l.next = s, Sn(r, t.memoizedState) || (Gt = true), t.memoizedState = r, t.baseState = a, t.baseQueue = l, n.lastRenderedState = r;
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
  function Vs(e) {
    var t = on(), n = t.queue;
    if (n === null) throw Error(j(311));
    n.lastRenderedReducer = e;
    var r = n.dispatch, i = n.pending, o = t.memoizedState;
    if (i !== null) {
      n.pending = null;
      var a = i = i.next;
      do
        o = e(o, a.action), a = a.next;
      while (a !== i);
      Sn(o, t.memoizedState) || (Gt = true), t.memoizedState = o, t.baseQueue === null && (t.baseState = o), n.lastRenderedState = o;
    }
    return [
      o,
      r
    ];
  }
  function Mh() {
  }
  function $h(e, t) {
    var n = $e, r = on(), i = t(), o = !Sn(r.memoizedState, i);
    if (o && (r.memoizedState = i, Gt = true), r = r.queue, Xu(Wh.bind(null, n, r, e), [
      e
    ]), r.getSnapshot !== t || o || ct !== null && ct.memoizedState.tag & 1) {
      if (n.flags |= 2048, ko(9, Hh.bind(null, n, r, i, t), void 0, null), dt === null) throw Error(j(349));
      Ir & 30 || jh(n, t, i);
    }
    return i;
  }
  function jh(e, t, n) {
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
  function Hh(e, t, n, r) {
    t.value = n, t.getSnapshot = r, Vh(t) && Kh(e);
  }
  function Wh(e, t, n) {
    return n(function() {
      Vh(t) && Kh(e);
    });
  }
  function Vh(e) {
    var t = e.getSnapshot;
    e = e.value;
    try {
      var n = t();
      return !Sn(e, n);
    } catch {
      return true;
    }
  }
  function Kh(e) {
    var t = Wn(e, 1);
    t !== null && En(t, e, 1, -1);
  }
  function ld(e) {
    var t = xn();
    return typeof e == "function" && (e = e()), t.memoizedState = t.baseState = e, e = {
      pending: null,
      interleaved: null,
      lanes: 0,
      dispatch: null,
      lastRenderedReducer: _o,
      lastRenderedState: e
    }, t.queue = e, e = e.dispatch = py.bind(null, $e, e), [
      t.memoizedState,
      e
    ];
  }
  function ko(e, t, n, r) {
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
  function Yh() {
    return on().memoizedState;
  }
  function ga(e, t, n, r) {
    var i = xn();
    $e.flags |= e, i.memoizedState = ko(1 | t, n, void 0, r === void 0 ? null : r);
  }
  function as(e, t, n, r) {
    var i = on();
    r = r === void 0 ? null : r;
    var o = void 0;
    if (rt !== null) {
      var a = rt.memoizedState;
      if (o = a.destroy, r !== null && Ku(r, a.deps)) {
        i.memoizedState = ko(t, n, o, r);
        return;
      }
    }
    $e.flags |= e, i.memoizedState = ko(1 | t, n, o, r);
  }
  function ud(e, t) {
    return ga(8390656, 8, e, t);
  }
  function Xu(e, t) {
    return as(2048, 8, e, t);
  }
  function Qh(e, t) {
    return as(4, 2, e, t);
  }
  function Xh(e, t) {
    return as(4, 4, e, t);
  }
  function Zh(e, t) {
    if (typeof t == "function") return e = e(), t(e), function() {
      t(null);
    };
    if (t != null) return e = e(), t.current = e, function() {
      t.current = null;
    };
  }
  function qh(e, t, n) {
    return n = n != null ? n.concat([
      e
    ]) : null, as(4, 4, Zh.bind(null, t, e), n);
  }
  function Zu() {
  }
  function Jh(e, t) {
    var n = on();
    t = t === void 0 ? null : t;
    var r = n.memoizedState;
    return r !== null && t !== null && Ku(t, r[1]) ? r[0] : (n.memoizedState = [
      e,
      t
    ], e);
  }
  function ep(e, t) {
    var n = on();
    t = t === void 0 ? null : t;
    var r = n.memoizedState;
    return r !== null && t !== null && Ku(t, r[1]) ? r[0] : (e = e(), n.memoizedState = [
      e,
      t
    ], e);
  }
  function tp(e, t, n) {
    return Ir & 21 ? (Sn(n, t) || (n = ah(), $e.lanes |= n, Fr |= n, e.baseState = true), t) : (e.baseState && (e.baseState = false, Gt = true), e.memoizedState = n);
  }
  function fy(e, t) {
    var n = Pe;
    Pe = n !== 0 && 4 > n ? n : 4, e(true);
    var r = Hs.transition;
    Hs.transition = {};
    try {
      e(false), t();
    } finally {
      Pe = n, Hs.transition = r;
    }
  }
  function np() {
    return on().memoizedState;
  }
  function hy(e, t, n) {
    var r = hr(e);
    if (n = {
      lane: r,
      action: n,
      hasEagerState: false,
      eagerState: null,
      next: null
    }, rp(e)) ip(t, n);
    else if (n = Gh(e, t, n, r), n !== null) {
      var i = Lt();
      En(n, e, r, i), op(n, t, r);
    }
  }
  function py(e, t, n) {
    var r = hr(e), i = {
      lane: r,
      action: n,
      hasEagerState: false,
      eagerState: null,
      next: null
    };
    if (rp(e)) ip(t, i);
    else {
      var o = e.alternate;
      if (e.lanes === 0 && (o === null || o.lanes === 0) && (o = t.lastRenderedReducer, o !== null)) try {
        var a = t.lastRenderedState, s = o(a, n);
        if (i.hasEagerState = true, i.eagerState = s, Sn(s, a)) {
          var l = t.interleaved;
          l === null ? (i.next = i, $u(t)) : (i.next = l.next, l.next = i), t.interleaved = i;
          return;
        }
      } catch {
      } finally {
      }
      n = Gh(e, t, i, r), n !== null && (i = Lt(), En(n, e, r, i), op(n, t, r));
    }
  }
  function rp(e) {
    var t = e.alternate;
    return e === $e || t !== null && t === $e;
  }
  function ip(e, t) {
    no = Ba = true;
    var n = e.pending;
    n === null ? t.next = t : (t.next = n.next, n.next = t), e.pending = t;
  }
  function op(e, t, n) {
    if (n & 4194240) {
      var r = t.lanes;
      r &= e.pendingLanes, n |= r, t.lanes = n, Ru(e, n);
    }
  }
  var Ma = {
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
  }, gy = {
    readContext: rn,
    useCallback: function(e, t) {
      return xn().memoizedState = [
        e,
        t === void 0 ? null : t
      ], e;
    },
    useContext: rn,
    useEffect: ud,
    useImperativeHandle: function(e, t, n) {
      return n = n != null ? n.concat([
        e
      ]) : null, ga(4194308, 4, Zh.bind(null, t, e), n);
    },
    useLayoutEffect: function(e, t) {
      return ga(4194308, 4, e, t);
    },
    useInsertionEffect: function(e, t) {
      return ga(4, 2, e, t);
    },
    useMemo: function(e, t) {
      var n = xn();
      return t = t === void 0 ? null : t, e = e(), n.memoizedState = [
        e,
        t
      ], e;
    },
    useReducer: function(e, t, n) {
      var r = xn();
      return t = n !== void 0 ? n(t) : t, r.memoizedState = r.baseState = t, e = {
        pending: null,
        interleaved: null,
        lanes: 0,
        dispatch: null,
        lastRenderedReducer: e,
        lastRenderedState: t
      }, r.queue = e, e = e.dispatch = hy.bind(null, $e, e), [
        r.memoizedState,
        e
      ];
    },
    useRef: function(e) {
      var t = xn();
      return e = {
        current: e
      }, t.memoizedState = e;
    },
    useState: ld,
    useDebugValue: Zu,
    useDeferredValue: function(e) {
      return xn().memoizedState = e;
    },
    useTransition: function() {
      var e = ld(false), t = e[0];
      return e = fy.bind(null, e[1]), xn().memoizedState = e, [
        t,
        e
      ];
    },
    useMutableSource: function() {
    },
    useSyncExternalStore: function(e, t, n) {
      var r = $e, i = xn();
      if (Ue) {
        if (n === void 0) throw Error(j(407));
        n = n();
      } else {
        if (n = t(), dt === null) throw Error(j(349));
        Ir & 30 || jh(r, t, n);
      }
      i.memoizedState = n;
      var o = {
        value: n,
        getSnapshot: t
      };
      return i.queue = o, ud(Wh.bind(null, r, o, e), [
        e
      ]), r.flags |= 2048, ko(9, Hh.bind(null, r, o, n, t), void 0, null), n;
    },
    useId: function() {
      var e = xn(), t = dt.identifierPrefix;
      if (Ue) {
        var n = Bn, r = Un;
        n = (r & ~(1 << 32 - wn(r) - 1)).toString(32) + n, t = ":" + t + "R" + n, n = So++, 0 < n && (t += "H" + n.toString(32)), t += ":";
      } else n = dy++, t = ":" + t + "r" + n.toString(32) + ":";
      return e.memoizedState = t;
    },
    unstable_isNewReconciler: false
  }, my = {
    readContext: rn,
    useCallback: Jh,
    useContext: rn,
    useEffect: Xu,
    useImperativeHandle: qh,
    useInsertionEffect: Qh,
    useLayoutEffect: Xh,
    useMemo: ep,
    useReducer: Ws,
    useRef: Yh,
    useState: function() {
      return Ws(_o);
    },
    useDebugValue: Zu,
    useDeferredValue: function(e) {
      var t = on();
      return tp(t, rt.memoizedState, e);
    },
    useTransition: function() {
      var e = Ws(_o)[0], t = on().memoizedState;
      return [
        e,
        t
      ];
    },
    useMutableSource: Mh,
    useSyncExternalStore: $h,
    useId: np,
    unstable_isNewReconciler: false
  }, vy = {
    readContext: rn,
    useCallback: Jh,
    useContext: rn,
    useEffect: Xu,
    useImperativeHandle: qh,
    useInsertionEffect: Qh,
    useLayoutEffect: Xh,
    useMemo: ep,
    useReducer: Vs,
    useRef: Yh,
    useState: function() {
      return Vs(_o);
    },
    useDebugValue: Zu,
    useDeferredValue: function(e) {
      var t = on();
      return rt === null ? t.memoizedState = e : tp(t, rt.memoizedState, e);
    },
    useTransition: function() {
      var e = Vs(_o)[0], t = on().memoizedState;
      return [
        e,
        t
      ];
    },
    useMutableSource: Mh,
    useSyncExternalStore: $h,
    useId: np,
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
  function Hl(e, t, n, r) {
    t = e.memoizedState, n = n(r, t), n = n == null ? t : je({}, t, n), e.memoizedState = n, e.lanes === 0 && (e.updateQueue.baseState = n);
  }
  var ss = {
    isMounted: function(e) {
      return (e = e._reactInternals) ? Or(e) === e : false;
    },
    enqueueSetState: function(e, t, n) {
      e = e._reactInternals;
      var r = Lt(), i = hr(e), o = Mn(r, i);
      o.payload = t, n != null && (o.callback = n), t = dr(e, o, i), t !== null && (En(t, e, i, r), ha(t, e, i));
    },
    enqueueReplaceState: function(e, t, n) {
      e = e._reactInternals;
      var r = Lt(), i = hr(e), o = Mn(r, i);
      o.tag = 1, o.payload = t, n != null && (o.callback = n), t = dr(e, o, i), t !== null && (En(t, e, i, r), ha(t, e, i));
    },
    enqueueForceUpdate: function(e, t) {
      e = e._reactInternals;
      var n = Lt(), r = hr(e), i = Mn(n, r);
      i.tag = 2, t != null && (i.callback = t), t = dr(e, i, r), t !== null && (En(t, e, r, n), ha(t, e, r));
    }
  };
  function cd(e, t, n, r, i, o, a) {
    return e = e.stateNode, typeof e.shouldComponentUpdate == "function" ? e.shouldComponentUpdate(r, o, a) : t.prototype && t.prototype.isPureReactComponent ? !go(n, r) || !go(i, o) : true;
  }
  function ap(e, t, n) {
    var r = false, i = mr, o = t.contextType;
    return typeof o == "object" && o !== null ? o = rn(o) : (i = Bt(t) ? Dr : Ct.current, r = t.contextTypes, o = (r = r != null) ? ui(e, i) : mr), t = new t(n, o), e.memoizedState = t.state !== null && t.state !== void 0 ? t.state : null, t.updater = ss, e.stateNode = t, t._reactInternals = e, r && (e = e.stateNode, e.__reactInternalMemoizedUnmaskedChildContext = i, e.__reactInternalMemoizedMaskedChildContext = o), t;
  }
  function dd(e, t, n, r) {
    e = t.state, typeof t.componentWillReceiveProps == "function" && t.componentWillReceiveProps(n, r), typeof t.UNSAFE_componentWillReceiveProps == "function" && t.UNSAFE_componentWillReceiveProps(n, r), t.state !== e && ss.enqueueReplaceState(t, t.state, null);
  }
  function Wl(e, t, n, r) {
    var i = e.stateNode;
    i.props = n, i.state = e.memoizedState, i.refs = {}, ju(e);
    var o = t.contextType;
    typeof o == "object" && o !== null ? i.context = rn(o) : (o = Bt(t) ? Dr : Ct.current, i.context = ui(e, o)), i.state = e.memoizedState, o = t.getDerivedStateFromProps, typeof o == "function" && (Hl(e, t, o, n), i.state = e.memoizedState), typeof t.getDerivedStateFromProps == "function" || typeof i.getSnapshotBeforeUpdate == "function" || typeof i.UNSAFE_componentWillMount != "function" && typeof i.componentWillMount != "function" || (t = i.state, typeof i.componentWillMount == "function" && i.componentWillMount(), typeof i.UNSAFE_componentWillMount == "function" && i.UNSAFE_componentWillMount(), t !== i.state && ss.enqueueReplaceState(i, i.state, null), Ga(e, n, i, r), i.state = e.memoizedState), typeof i.componentDidMount == "function" && (e.flags |= 4194308);
  }
  function hi(e, t) {
    try {
      var n = "", r = t;
      do
        n += Wm(r), r = r.return;
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
  function Ks(e, t, n) {
    return {
      value: e,
      source: null,
      stack: n ?? null,
      digest: t ?? null
    };
  }
  function Vl(e, t) {
    try {
      console.error(t.value);
    } catch (n) {
      setTimeout(function() {
        throw n;
      });
    }
  }
  var yy = typeof WeakMap == "function" ? WeakMap : Map;
  function sp(e, t, n) {
    n = Mn(-1, n), n.tag = 3, n.payload = {
      element: null
    };
    var r = t.value;
    return n.callback = function() {
      ja || (ja = true, nu = r), Vl(e, t);
    }, n;
  }
  function lp(e, t, n) {
    n = Mn(-1, n), n.tag = 3;
    var r = e.type.getDerivedStateFromError;
    if (typeof r == "function") {
      var i = t.value;
      n.payload = function() {
        return r(i);
      }, n.callback = function() {
        Vl(e, t);
      };
    }
    var o = e.stateNode;
    return o !== null && typeof o.componentDidCatch == "function" && (n.callback = function() {
      Vl(e, t), typeof r != "function" && (fr === null ? fr = /* @__PURE__ */ new Set([
        this
      ]) : fr.add(this));
      var a = t.stack;
      this.componentDidCatch(t.value, {
        componentStack: a !== null ? a : ""
      });
    }), n;
  }
  function fd(e, t, n) {
    var r = e.pingCache;
    if (r === null) {
      r = e.pingCache = new yy();
      var i = /* @__PURE__ */ new Set();
      r.set(t, i);
    } else i = r.get(t), i === void 0 && (i = /* @__PURE__ */ new Set(), r.set(t, i));
    i.has(n) || (i.add(n), e = Py.bind(null, e, t, n), t.then(e, e));
  }
  function hd(e) {
    do {
      var t;
      if ((t = e.tag === 13) && (t = e.memoizedState, t = t !== null ? t.dehydrated !== null : true), t) return e;
      e = e.return;
    } while (e !== null);
    return null;
  }
  function pd(e, t, n, r, i) {
    return e.mode & 1 ? (e.flags |= 65536, e.lanes = i, e) : (e === t ? e.flags |= 65536 : (e.flags |= 128, n.flags |= 131072, n.flags &= -52805, n.tag === 1 && (n.alternate === null ? n.tag = 17 : (t = Mn(-1, 1), t.tag = 2, dr(n, t, 1))), n.lanes |= 1), e);
  }
  var wy = Kn.ReactCurrentOwner, Gt = false;
  function At(e, t, n, r) {
    t.child = e === null ? Oh(t, null, n, r) : di(t, e.child, n, r);
  }
  function gd(e, t, n, r, i) {
    n = n.render;
    var o = t.ref;
    return ii(t, i), r = Yu(e, t, n, r, o, i), n = Qu(), e !== null && !Gt ? (t.updateQueue = e.updateQueue, t.flags &= -2053, e.lanes &= ~i, Vn(e, t, i)) : (Ue && n && zu(t), t.flags |= 1, At(e, t, r, i), t.child);
  }
  function md(e, t, n, r, i) {
    if (e === null) {
      var o = n.type;
      return typeof o == "function" && !oc(o) && o.defaultProps === void 0 && n.compare === null && n.defaultProps === void 0 ? (t.tag = 15, t.type = o, up(e, t, o, r, i)) : (e = wa(n.type, null, r, t, t.mode, i), e.ref = t.ref, e.return = t, t.child = e);
    }
    if (o = e.child, !(e.lanes & i)) {
      var a = o.memoizedProps;
      if (n = n.compare, n = n !== null ? n : go, n(a, r) && e.ref === t.ref) return Vn(e, t, i);
    }
    return t.flags |= 1, e = pr(o, r), e.ref = t.ref, e.return = t, t.child = e;
  }
  function up(e, t, n, r, i) {
    if (e !== null) {
      var o = e.memoizedProps;
      if (go(o, r) && e.ref === t.ref) if (Gt = false, t.pendingProps = r = o, (e.lanes & i) !== 0) e.flags & 131072 && (Gt = true);
      else return t.lanes = e.lanes, Vn(e, t, i);
    }
    return Kl(e, t, n, r, i);
  }
  function cp(e, t, n) {
    var r = t.pendingProps, i = r.children, o = e !== null ? e.memoizedState : null;
    if (r.mode === "hidden") if (!(t.mode & 1)) t.memoizedState = {
      baseLanes: 0,
      cachePool: null,
      transitions: null
    }, Ne(Jr, jt), jt |= n;
    else {
      if (!(n & 1073741824)) return e = o !== null ? o.baseLanes | n : n, t.lanes = t.childLanes = 1073741824, t.memoizedState = {
        baseLanes: e,
        cachePool: null,
        transitions: null
      }, t.updateQueue = null, Ne(Jr, jt), jt |= e, null;
      t.memoizedState = {
        baseLanes: 0,
        cachePool: null,
        transitions: null
      }, r = o !== null ? o.baseLanes : n, Ne(Jr, jt), jt |= r;
    }
    else o !== null ? (r = o.baseLanes | n, t.memoizedState = null) : r = n, Ne(Jr, jt), jt |= r;
    return At(e, t, i, n), t.child;
  }
  function dp(e, t) {
    var n = t.ref;
    (e === null && n !== null || e !== null && e.ref !== n) && (t.flags |= 512, t.flags |= 2097152);
  }
  function Kl(e, t, n, r, i) {
    var o = Bt(n) ? Dr : Ct.current;
    return o = ui(t, o), ii(t, i), n = Yu(e, t, n, r, o, i), r = Qu(), e !== null && !Gt ? (t.updateQueue = e.updateQueue, t.flags &= -2053, e.lanes &= ~i, Vn(e, t, i)) : (Ue && r && zu(t), t.flags |= 1, At(e, t, n, i), t.child);
  }
  function vd(e, t, n, r, i) {
    if (Bt(n)) {
      var o = true;
      Ia(t);
    } else o = false;
    if (ii(t, i), t.stateNode === null) ma(e, t), ap(t, n, r), Wl(t, n, r, i), r = true;
    else if (e === null) {
      var a = t.stateNode, s = t.memoizedProps;
      a.props = s;
      var l = a.context, c = n.contextType;
      typeof c == "object" && c !== null ? c = rn(c) : (c = Bt(n) ? Dr : Ct.current, c = ui(t, c));
      var h = n.getDerivedStateFromProps, f = typeof h == "function" || typeof a.getSnapshotBeforeUpdate == "function";
      f || typeof a.UNSAFE_componentWillReceiveProps != "function" && typeof a.componentWillReceiveProps != "function" || (s !== r || l !== c) && dd(t, a, r, c), nr = false;
      var p = t.memoizedState;
      a.state = p, Ga(t, r, a, i), l = t.memoizedState, s !== r || p !== l || Ut.current || nr ? (typeof h == "function" && (Hl(t, n, h, r), l = t.memoizedState), (s = nr || cd(t, n, s, r, p, l, c)) ? (f || typeof a.UNSAFE_componentWillMount != "function" && typeof a.componentWillMount != "function" || (typeof a.componentWillMount == "function" && a.componentWillMount(), typeof a.UNSAFE_componentWillMount == "function" && a.UNSAFE_componentWillMount()), typeof a.componentDidMount == "function" && (t.flags |= 4194308)) : (typeof a.componentDidMount == "function" && (t.flags |= 4194308), t.memoizedProps = r, t.memoizedState = l), a.props = r, a.state = l, a.context = c, r = s) : (typeof a.componentDidMount == "function" && (t.flags |= 4194308), r = false);
    } else {
      a = t.stateNode, Uh(e, t), s = t.memoizedProps, c = t.type === t.elementType ? s : gn(t.type, s), a.props = c, f = t.pendingProps, p = a.context, l = n.contextType, typeof l == "object" && l !== null ? l = rn(l) : (l = Bt(n) ? Dr : Ct.current, l = ui(t, l));
      var y = n.getDerivedStateFromProps;
      (h = typeof y == "function" || typeof a.getSnapshotBeforeUpdate == "function") || typeof a.UNSAFE_componentWillReceiveProps != "function" && typeof a.componentWillReceiveProps != "function" || (s !== f || p !== l) && dd(t, a, r, l), nr = false, p = t.memoizedState, a.state = p, Ga(t, r, a, i);
      var k = t.memoizedState;
      s !== f || p !== k || Ut.current || nr ? (typeof y == "function" && (Hl(t, n, y, r), k = t.memoizedState), (c = nr || cd(t, n, c, r, p, k, l) || false) ? (h || typeof a.UNSAFE_componentWillUpdate != "function" && typeof a.componentWillUpdate != "function" || (typeof a.componentWillUpdate == "function" && a.componentWillUpdate(r, k, l), typeof a.UNSAFE_componentWillUpdate == "function" && a.UNSAFE_componentWillUpdate(r, k, l)), typeof a.componentDidUpdate == "function" && (t.flags |= 4), typeof a.getSnapshotBeforeUpdate == "function" && (t.flags |= 1024)) : (typeof a.componentDidUpdate != "function" || s === e.memoizedProps && p === e.memoizedState || (t.flags |= 4), typeof a.getSnapshotBeforeUpdate != "function" || s === e.memoizedProps && p === e.memoizedState || (t.flags |= 1024), t.memoizedProps = r, t.memoizedState = k), a.props = r, a.state = k, a.context = l, r = c) : (typeof a.componentDidUpdate != "function" || s === e.memoizedProps && p === e.memoizedState || (t.flags |= 4), typeof a.getSnapshotBeforeUpdate != "function" || s === e.memoizedProps && p === e.memoizedState || (t.flags |= 1024), r = false);
    }
    return Yl(e, t, n, r, o, i);
  }
  function Yl(e, t, n, r, i, o) {
    dp(e, t);
    var a = (t.flags & 128) !== 0;
    if (!r && !a) return i && nd(t, n, false), Vn(e, t, o);
    r = t.stateNode, wy.current = t;
    var s = a && typeof n.getDerivedStateFromError != "function" ? null : r.render();
    return t.flags |= 1, e !== null && a ? (t.child = di(t, e.child, null, o), t.child = di(t, null, s, o)) : At(e, t, s, o), t.memoizedState = r.state, i && nd(t, n, true), t.child;
  }
  function fp(e) {
    var t = e.stateNode;
    t.pendingContext ? td(e, t.pendingContext, t.pendingContext !== t.context) : t.context && td(e, t.context, false), Hu(e, t.containerInfo);
  }
  function yd(e, t, n, r, i) {
    return ci(), Gu(i), t.flags |= 256, At(e, t, n, r), t.child;
  }
  var Ql = {
    dehydrated: null,
    treeContext: null,
    retryLane: 0
  };
  function Xl(e) {
    return {
      baseLanes: e,
      cachePool: null,
      transitions: null
    };
  }
  function hp(e, t, n) {
    var r = t.pendingProps, i = Me.current, o = false, a = (t.flags & 128) !== 0, s;
    if ((s = a) || (s = e !== null && e.memoizedState === null ? false : (i & 2) !== 0), s ? (o = true, t.flags &= -129) : (e === null || e.memoizedState !== null) && (i |= 1), Ne(Me, i & 1), e === null) return $l(t), e = t.memoizedState, e !== null && (e = e.dehydrated, e !== null) ? (t.mode & 1 ? e.data === "$!" ? t.lanes = 8 : t.lanes = 1073741824 : t.lanes = 1, null) : (a = r.children, e = r.fallback, o ? (r = t.mode, o = t.child, a = {
      mode: "hidden",
      children: a
    }, !(r & 1) && o !== null ? (o.childLanes = 0, o.pendingProps = a) : o = cs(a, r, 0, null), e = Lr(e, r, n, null), o.return = t, e.return = t, o.sibling = e, t.child = o, t.child.memoizedState = Xl(n), t.memoizedState = Ql, e) : qu(t, a));
    if (i = e.memoizedState, i !== null && (s = i.dehydrated, s !== null)) return Ey(e, t, a, r, s, i, n);
    if (o) {
      o = r.fallback, a = t.mode, i = e.child, s = i.sibling;
      var l = {
        mode: "hidden",
        children: r.children
      };
      return !(a & 1) && t.child !== i ? (r = t.child, r.childLanes = 0, r.pendingProps = l, t.deletions = null) : (r = pr(i, l), r.subtreeFlags = i.subtreeFlags & 14680064), s !== null ? o = pr(s, o) : (o = Lr(o, a, n, null), o.flags |= 2), o.return = t, r.return = t, r.sibling = o, t.child = r, r = o, o = t.child, a = e.child.memoizedState, a = a === null ? Xl(n) : {
        baseLanes: a.baseLanes | n,
        cachePool: null,
        transitions: a.transitions
      }, o.memoizedState = a, o.childLanes = e.childLanes & ~n, t.memoizedState = Ql, r;
    }
    return o = e.child, e = o.sibling, r = pr(o, {
      mode: "visible",
      children: r.children
    }), !(t.mode & 1) && (r.lanes = n), r.return = t, r.sibling = null, e !== null && (n = t.deletions, n === null ? (t.deletions = [
      e
    ], t.flags |= 16) : n.push(e)), t.child = r, t.memoizedState = null, r;
  }
  function qu(e, t) {
    return t = cs({
      mode: "visible",
      children: t
    }, e.mode, 0, null), t.return = e, e.child = t;
  }
  function Qo(e, t, n, r) {
    return r !== null && Gu(r), di(t, e.child, null, n), e = qu(t, t.pendingProps.children), e.flags |= 2, t.memoizedState = null, e;
  }
  function Ey(e, t, n, r, i, o, a) {
    if (n) return t.flags & 256 ? (t.flags &= -257, r = Ks(Error(j(422))), Qo(e, t, a, r)) : t.memoizedState !== null ? (t.child = e.child, t.flags |= 128, null) : (o = r.fallback, i = t.mode, r = cs({
      mode: "visible",
      children: r.children
    }, i, 0, null), o = Lr(o, i, a, null), o.flags |= 2, r.return = t, o.return = t, r.sibling = o, t.child = r, t.mode & 1 && di(t, e.child, null, a), t.child.memoizedState = Xl(a), t.memoizedState = Ql, o);
    if (!(t.mode & 1)) return Qo(e, t, a, null);
    if (i.data === "$!") {
      if (r = i.nextSibling && i.nextSibling.dataset, r) var s = r.dgst;
      return r = s, o = Error(j(419)), r = Ks(o, r, void 0), Qo(e, t, a, r);
    }
    if (s = (a & e.childLanes) !== 0, Gt || s) {
      if (r = dt, r !== null) {
        switch (a & -a) {
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
        i = i & (r.suspendedLanes | a) ? 0 : i, i !== 0 && i !== o.retryLane && (o.retryLane = i, Wn(e, i), En(r, e, i, -1));
      }
      return ic(), r = Ks(Error(j(421))), Qo(e, t, a, r);
    }
    return i.data === "$?" ? (t.flags |= 128, t.child = e.child, t = Iy.bind(null, e), i._reactRetry = t, null) : (e = o.treeContext, Ht = cr(i.nextSibling), Wt = t, Ue = true, vn = null, e !== null && (qt[Jt++] = Un, qt[Jt++] = Bn, qt[Jt++] = Pr, Un = e.id, Bn = e.overflow, Pr = t), t = qu(t, r.children), t.flags |= 4096, t);
  }
  function wd(e, t, n) {
    e.lanes |= t;
    var r = e.alternate;
    r !== null && (r.lanes |= t), jl(e.return, t, n);
  }
  function Ys(e, t, n, r, i) {
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
  function pp(e, t, n) {
    var r = t.pendingProps, i = r.revealOrder, o = r.tail;
    if (At(e, t, r.children, n), r = Me.current, r & 2) r = r & 1 | 2, t.flags |= 128;
    else {
      if (e !== null && e.flags & 128) e: for (e = t.child; e !== null; ) {
        if (e.tag === 13) e.memoizedState !== null && wd(e, n, t);
        else if (e.tag === 19) wd(e, n, t);
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
    if (Ne(Me, r), !(t.mode & 1)) t.memoizedState = null;
    else switch (i) {
      case "forwards":
        for (n = t.child, i = null; n !== null; ) e = n.alternate, e !== null && Ua(e) === null && (i = n), n = n.sibling;
        n = i, n === null ? (i = t.child, t.child = null) : (i = n.sibling, n.sibling = null), Ys(t, false, i, n, o);
        break;
      case "backwards":
        for (n = null, i = t.child, t.child = null; i !== null; ) {
          if (e = i.alternate, e !== null && Ua(e) === null) {
            t.child = i;
            break;
          }
          e = i.sibling, i.sibling = n, n = i, i = e;
        }
        Ys(t, true, n, null, o);
        break;
      case "together":
        Ys(t, false, null, null, void 0);
        break;
      default:
        t.memoizedState = null;
    }
    return t.child;
  }
  function ma(e, t) {
    !(t.mode & 1) && e !== null && (e.alternate = null, t.alternate = null, t.flags |= 2);
  }
  function Vn(e, t, n) {
    if (e !== null && (t.dependencies = e.dependencies), Fr |= t.lanes, !(n & t.childLanes)) return null;
    if (e !== null && t.child !== e.child) throw Error(j(153));
    if (t.child !== null) {
      for (e = t.child, n = pr(e, e.pendingProps), t.child = n, n.return = t; e.sibling !== null; ) e = e.sibling, n = n.sibling = pr(e, e.pendingProps), n.return = t;
      n.sibling = null;
    }
    return t.child;
  }
  function Sy(e, t, n) {
    switch (t.tag) {
      case 3:
        fp(t), ci();
        break;
      case 5:
        Bh(t);
        break;
      case 1:
        Bt(t.type) && Ia(t);
        break;
      case 4:
        Hu(t, t.stateNode.containerInfo);
        break;
      case 10:
        var r = t.type._context, i = t.memoizedProps.value;
        Ne(za, r._currentValue), r._currentValue = i;
        break;
      case 13:
        if (r = t.memoizedState, r !== null) return r.dehydrated !== null ? (Ne(Me, Me.current & 1), t.flags |= 128, null) : n & t.child.childLanes ? hp(e, t, n) : (Ne(Me, Me.current & 1), e = Vn(e, t, n), e !== null ? e.sibling : null);
        Ne(Me, Me.current & 1);
        break;
      case 19:
        if (r = (n & t.childLanes) !== 0, e.flags & 128) {
          if (r) return pp(e, t, n);
          t.flags |= 128;
        }
        if (i = t.memoizedState, i !== null && (i.rendering = null, i.tail = null, i.lastEffect = null), Ne(Me, Me.current), r) break;
        return null;
      case 22:
      case 23:
        return t.lanes = 0, cp(e, t, n);
    }
    return Vn(e, t, n);
  }
  var gp, Zl, mp, vp;
  gp = function(e, t) {
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
  Zl = function() {
  };
  mp = function(e, t, n, r) {
    var i = e.memoizedProps;
    if (i !== r) {
      e = t.stateNode, Rr(Ln.current);
      var o = null;
      switch (n) {
        case "input":
          i = wl(e, i), r = wl(e, r), o = [];
          break;
        case "select":
          i = je({}, i, {
            value: void 0
          }), r = je({}, r, {
            value: void 0
          }), o = [];
          break;
        case "textarea":
          i = _l(e, i), r = _l(e, r), o = [];
          break;
        default:
          typeof i.onClick != "function" && typeof r.onClick == "function" && (e.onclick = Da);
      }
      bl(n, r);
      var a;
      n = null;
      for (c in i) if (!r.hasOwnProperty(c) && i.hasOwnProperty(c) && i[c] != null) if (c === "style") {
        var s = i[c];
        for (a in s) s.hasOwnProperty(a) && (n || (n = {}), n[a] = "");
      } else c !== "dangerouslySetInnerHTML" && c !== "children" && c !== "suppressContentEditableWarning" && c !== "suppressHydrationWarning" && c !== "autoFocus" && (so.hasOwnProperty(c) ? o || (o = []) : (o = o || []).push(c, null));
      for (c in r) {
        var l = r[c];
        if (s = i == null ? void 0 : i[c], r.hasOwnProperty(c) && l !== s && (l != null || s != null)) if (c === "style") if (s) {
          for (a in s) !s.hasOwnProperty(a) || l && l.hasOwnProperty(a) || (n || (n = {}), n[a] = "");
          for (a in l) l.hasOwnProperty(a) && s[a] !== l[a] && (n || (n = {}), n[a] = l[a]);
        } else n || (o || (o = []), o.push(c, n)), n = l;
        else c === "dangerouslySetInnerHTML" ? (l = l ? l.__html : void 0, s = s ? s.__html : void 0, l != null && s !== l && (o = o || []).push(c, l)) : c === "children" ? typeof l != "string" && typeof l != "number" || (o = o || []).push(c, "" + l) : c !== "suppressContentEditableWarning" && c !== "suppressHydrationWarning" && (so.hasOwnProperty(c) ? (l != null && c === "onScroll" && Oe("scroll", e), o || s === l || (o = [])) : (o = o || []).push(c, l));
      }
      n && (o = o || []).push("style", n);
      var c = o;
      (t.updateQueue = c) && (t.flags |= 4);
    }
  };
  vp = function(e, t, n, r) {
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
  function _y(e, t, n) {
    var r = t.pendingProps;
    switch (Ou(t), t.tag) {
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
        return Bt(t.type) && Pa(), _t(t), null;
      case 3:
        return r = t.stateNode, fi(), Ge(Ut), Ge(Ct), Vu(), r.pendingContext && (r.context = r.pendingContext, r.pendingContext = null), (e === null || e.child === null) && (Ko(t) ? t.flags |= 4 : e === null || e.memoizedState.isDehydrated && !(t.flags & 256) || (t.flags |= 1024, vn !== null && (ou(vn), vn = null))), Zl(e, t), _t(t), null;
      case 5:
        Wu(t);
        var i = Rr(Eo.current);
        if (n = t.type, e !== null && t.stateNode != null) mp(e, t, n, r, i), e.ref !== t.ref && (t.flags |= 512, t.flags |= 2097152);
        else {
          if (!r) {
            if (t.stateNode === null) throw Error(j(166));
            return _t(t), null;
          }
          if (e = Rr(Ln.current), Ko(t)) {
            r = t.stateNode, n = t.type;
            var o = t.memoizedProps;
            switch (r[Tn] = t, r[yo] = o, e = (t.mode & 1) !== 0, n) {
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
                for (i = 0; i < Qi.length; i++) Oe(Qi[i], r);
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
                Rc(r, o), Oe("invalid", r);
                break;
              case "select":
                r._wrapperState = {
                  wasMultiple: !!o.multiple
                }, Oe("invalid", r);
                break;
              case "textarea":
                Lc(r, o), Oe("invalid", r);
            }
            bl(n, o), i = null;
            for (var a in o) if (o.hasOwnProperty(a)) {
              var s = o[a];
              a === "children" ? typeof s == "string" ? r.textContent !== s && (o.suppressHydrationWarning !== true && Vo(r.textContent, s, e), i = [
                "children",
                s
              ]) : typeof s == "number" && r.textContent !== "" + s && (o.suppressHydrationWarning !== true && Vo(r.textContent, s, e), i = [
                "children",
                "" + s
              ]) : so.hasOwnProperty(a) && s != null && a === "onScroll" && Oe("scroll", r);
            }
            switch (n) {
              case "input":
                Go(r), Ac(r, o, true);
                break;
              case "textarea":
                Go(r), Dc(r);
                break;
              case "select":
              case "option":
                break;
              default:
                typeof o.onClick == "function" && (r.onclick = Da);
            }
            r = i, t.updateQueue = r, r !== null && (t.flags |= 4);
          } else {
            a = i.nodeType === 9 ? i : i.ownerDocument, e === "http://www.w3.org/1999/xhtml" && (e = Wf(n)), e === "http://www.w3.org/1999/xhtml" ? n === "script" ? (e = a.createElement("div"), e.innerHTML = "<script><\/script>", e = e.removeChild(e.firstChild)) : typeof r.is == "string" ? e = a.createElement(n, {
              is: r.is
            }) : (e = a.createElement(n), n === "select" && (a = e, r.multiple ? a.multiple = true : r.size && (a.size = r.size))) : e = a.createElementNS(e, n), e[Tn] = t, e[yo] = r, gp(e, t, false, false), t.stateNode = e;
            e: {
              switch (a = Cl(n, r), n) {
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
                  for (i = 0; i < Qi.length; i++) Oe(Qi[i], e);
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
                  Rc(e, r), i = wl(e, r), Oe("invalid", e);
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
                  Lc(e, r), i = _l(e, r), Oe("invalid", e);
                  break;
                default:
                  i = r;
              }
              bl(n, i), s = i;
              for (o in s) if (s.hasOwnProperty(o)) {
                var l = s[o];
                o === "style" ? Yf(e, l) : o === "dangerouslySetInnerHTML" ? (l = l ? l.__html : void 0, l != null && Vf(e, l)) : o === "children" ? typeof l == "string" ? (n !== "textarea" || l !== "") && lo(e, l) : typeof l == "number" && lo(e, "" + l) : o !== "suppressContentEditableWarning" && o !== "suppressHydrationWarning" && o !== "autoFocus" && (so.hasOwnProperty(o) ? l != null && o === "onScroll" && Oe("scroll", e) : l != null && _u(e, o, l, a));
              }
              switch (n) {
                case "input":
                  Go(e), Ac(e, r, false);
                  break;
                case "textarea":
                  Go(e), Dc(e);
                  break;
                case "option":
                  r.value != null && e.setAttribute("value", "" + gr(r.value));
                  break;
                case "select":
                  e.multiple = !!r.multiple, o = r.value, o != null ? ei(e, !!r.multiple, o, false) : r.defaultValue != null && ei(e, !!r.multiple, r.defaultValue, true);
                  break;
                default:
                  typeof i.onClick == "function" && (e.onclick = Da);
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
        if (e && t.stateNode != null) vp(e, t, e.memoizedProps, r);
        else {
          if (typeof r != "string" && t.stateNode === null) throw Error(j(166));
          if (n = Rr(Eo.current), Rr(Ln.current), Ko(t)) {
            if (r = t.stateNode, n = t.memoizedProps, r[Tn] = t, (o = r.nodeValue !== n) && (e = Wt, e !== null)) switch (e.tag) {
              case 3:
                Vo(r.nodeValue, n, (e.mode & 1) !== 0);
                break;
              case 5:
                e.memoizedProps.suppressHydrationWarning !== true && Vo(r.nodeValue, n, (e.mode & 1) !== 0);
            }
            o && (t.flags |= 4);
          } else r = (n.nodeType === 9 ? n : n.ownerDocument).createTextNode(r), r[Tn] = t, t.stateNode = r;
        }
        return _t(t), null;
      case 13:
        if (Ge(Me), r = t.memoizedState, e === null || e.memoizedState !== null && e.memoizedState.dehydrated !== null) {
          if (Ue && Ht !== null && t.mode & 1 && !(t.flags & 128)) Nh(), ci(), t.flags |= 98560, o = false;
          else if (o = Ko(t), r !== null && r.dehydrated !== null) {
            if (e === null) {
              if (!o) throw Error(j(318));
              if (o = t.memoizedState, o = o !== null ? o.dehydrated : null, !o) throw Error(j(317));
              o[Tn] = t;
            } else ci(), !(t.flags & 128) && (t.memoizedState = null), t.flags |= 4;
            _t(t), o = false;
          } else vn !== null && (ou(vn), vn = null), o = true;
          if (!o) return t.flags & 65536 ? t : null;
        }
        return t.flags & 128 ? (t.lanes = n, t) : (r = r !== null, r !== (e !== null && e.memoizedState !== null) && r && (t.child.flags |= 8192, t.mode & 1 && (e === null || Me.current & 1 ? ot === 0 && (ot = 3) : ic())), t.updateQueue !== null && (t.flags |= 4), _t(t), null);
      case 4:
        return fi(), Zl(e, t), e === null && mo(t.stateNode.containerInfo), _t(t), null;
      case 10:
        return Mu(t.type._context), _t(t), null;
      case 17:
        return Bt(t.type) && Pa(), _t(t), null;
      case 19:
        if (Ge(Me), o = t.memoizedState, o === null) return _t(t), null;
        if (r = (t.flags & 128) !== 0, a = o.rendering, a === null) if (r) Fi(o, false);
        else {
          if (ot !== 0 || e !== null && e.flags & 128) for (e = t.child; e !== null; ) {
            if (a = Ua(e), a !== null) {
              for (t.flags |= 128, Fi(o, false), r = a.updateQueue, r !== null && (t.updateQueue = r, t.flags |= 4), t.subtreeFlags = 0, r = n, n = t.child; n !== null; ) o = n, e = r, o.flags &= 14680066, a = o.alternate, a === null ? (o.childLanes = 0, o.lanes = e, o.child = null, o.subtreeFlags = 0, o.memoizedProps = null, o.memoizedState = null, o.updateQueue = null, o.dependencies = null, o.stateNode = null) : (o.childLanes = a.childLanes, o.lanes = a.lanes, o.child = a.child, o.subtreeFlags = 0, o.deletions = null, o.memoizedProps = a.memoizedProps, o.memoizedState = a.memoizedState, o.updateQueue = a.updateQueue, o.type = a.type, e = a.dependencies, o.dependencies = e === null ? null : {
                lanes: e.lanes,
                firstContext: e.firstContext
              }), n = n.sibling;
              return Ne(Me, Me.current & 1 | 2), t.child;
            }
            e = e.sibling;
          }
          o.tail !== null && Ze() > pi && (t.flags |= 128, r = true, Fi(o, false), t.lanes = 4194304);
        }
        else {
          if (!r) if (e = Ua(a), e !== null) {
            if (t.flags |= 128, r = true, n = e.updateQueue, n !== null && (t.updateQueue = n, t.flags |= 4), Fi(o, true), o.tail === null && o.tailMode === "hidden" && !a.alternate && !Ue) return _t(t), null;
          } else 2 * Ze() - o.renderingStartTime > pi && n !== 1073741824 && (t.flags |= 128, r = true, Fi(o, false), t.lanes = 4194304);
          o.isBackwards ? (a.sibling = t.child, t.child = a) : (n = o.last, n !== null ? n.sibling = a : t.child = a, o.last = a);
        }
        return o.tail !== null ? (t = o.tail, o.rendering = t, o.tail = t.sibling, o.renderingStartTime = Ze(), t.sibling = null, n = Me.current, Ne(Me, r ? n & 1 | 2 : n & 1), t) : (_t(t), null);
      case 22:
      case 23:
        return rc(), r = t.memoizedState !== null, e !== null && e.memoizedState !== null !== r && (t.flags |= 8192), r && t.mode & 1 ? jt & 1073741824 && (_t(t), t.subtreeFlags & 6 && (t.flags |= 8192)) : _t(t), null;
      case 24:
        return null;
      case 25:
        return null;
    }
    throw Error(j(156, t.tag));
  }
  function ky(e, t) {
    switch (Ou(t), t.tag) {
      case 1:
        return Bt(t.type) && Pa(), e = t.flags, e & 65536 ? (t.flags = e & -65537 | 128, t) : null;
      case 3:
        return fi(), Ge(Ut), Ge(Ct), Vu(), e = t.flags, e & 65536 && !(e & 128) ? (t.flags = e & -65537 | 128, t) : null;
      case 5:
        return Wu(t), null;
      case 13:
        if (Ge(Me), e = t.memoizedState, e !== null && e.dehydrated !== null) {
          if (t.alternate === null) throw Error(j(340));
          ci();
        }
        return e = t.flags, e & 65536 ? (t.flags = e & -65537 | 128, t) : null;
      case 19:
        return Ge(Me), null;
      case 4:
        return fi(), null;
      case 10:
        return Mu(t.type._context), null;
      case 22:
      case 23:
        return rc(), null;
      case 24:
        return null;
      default:
        return null;
    }
  }
  var Xo = false, bt = false, by = typeof WeakSet == "function" ? WeakSet : Set, J = null;
  function qr(e, t) {
    var n = e.ref;
    if (n !== null) if (typeof n == "function") try {
      n(null);
    } catch (r) {
      Ye(e, t, r);
    }
    else n.current = null;
  }
  function ql(e, t, n) {
    try {
      n();
    } catch (r) {
      Ye(e, t, r);
    }
  }
  var Ed = false;
  function Cy(e, t) {
    if (Nl = Ra, e = _h(), Nu(e)) {
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
          var a = 0, s = -1, l = -1, c = 0, h = 0, f = e, p = null;
          t: for (; ; ) {
            for (var y; f !== n || i !== 0 && f.nodeType !== 3 || (s = a + i), f !== o || r !== 0 && f.nodeType !== 3 || (l = a + r), f.nodeType === 3 && (a += f.nodeValue.length), (y = f.firstChild) !== null; ) p = f, f = y;
            for (; ; ) {
              if (f === e) break t;
              if (p === n && ++c === i && (s = a), p === o && ++h === r && (l = a), (y = f.nextSibling) !== null) break;
              f = p, p = f.parentNode;
            }
            f = y;
          }
          n = s === -1 || l === -1 ? null : {
            start: s,
            end: l
          };
        } else n = null;
      }
      n = n || {
        start: 0,
        end: 0
      };
    } else n = null;
    for (zl = {
      focusedElem: e,
      selectionRange: n
    }, Ra = false, J = t; J !== null; ) if (t = J, e = t.child, (t.subtreeFlags & 1028) !== 0 && e !== null) e.return = t, J = e;
    else for (; J !== null; ) {
      t = J;
      try {
        var k = t.alternate;
        if (t.flags & 1024) switch (t.tag) {
          case 0:
          case 11:
          case 15:
            break;
          case 1:
            if (k !== null) {
              var b = k.memoizedProps, I = k.memoizedState, S = t.stateNode, m = S.getSnapshotBeforeUpdate(t.elementType === t.type ? b : gn(t.type, b), I);
              S.__reactInternalSnapshotBeforeUpdate = m;
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
            throw Error(j(163));
        }
      } catch (E) {
        Ye(t, t.return, E);
      }
      if (e = t.sibling, e !== null) {
        e.return = t.return, J = e;
        break;
      }
      J = t.return;
    }
    return k = Ed, Ed = false, k;
  }
  function ro(e, t, n) {
    var r = t.updateQueue;
    if (r = r !== null ? r.lastEffect : null, r !== null) {
      var i = r = r.next;
      do {
        if ((i.tag & e) === e) {
          var o = i.destroy;
          i.destroy = void 0, o !== void 0 && ql(t, n, o);
        }
        i = i.next;
      } while (i !== r);
    }
  }
  function ls(e, t) {
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
  function Jl(e) {
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
  function yp(e) {
    var t = e.alternate;
    t !== null && (e.alternate = null, yp(t)), e.child = null, e.deletions = null, e.sibling = null, e.tag === 5 && (t = e.stateNode, t !== null && (delete t[Tn], delete t[yo], delete t[Ul], delete t[sy], delete t[ly])), e.stateNode = null, e.return = null, e.dependencies = null, e.memoizedProps = null, e.memoizedState = null, e.pendingProps = null, e.stateNode = null, e.updateQueue = null;
  }
  function wp(e) {
    return e.tag === 5 || e.tag === 3 || e.tag === 4;
  }
  function Sd(e) {
    e: for (; ; ) {
      for (; e.sibling === null; ) {
        if (e.return === null || wp(e.return)) return null;
        e = e.return;
      }
      for (e.sibling.return = e.return, e = e.sibling; e.tag !== 5 && e.tag !== 6 && e.tag !== 18; ) {
        if (e.flags & 2 || e.child === null || e.tag === 4) continue e;
        e.child.return = e, e = e.child;
      }
      if (!(e.flags & 2)) return e.stateNode;
    }
  }
  function eu(e, t, n) {
    var r = e.tag;
    if (r === 5 || r === 6) e = e.stateNode, t ? n.nodeType === 8 ? n.parentNode.insertBefore(e, t) : n.insertBefore(e, t) : (n.nodeType === 8 ? (t = n.parentNode, t.insertBefore(e, n)) : (t = n, t.appendChild(e)), n = n._reactRootContainer, n != null || t.onclick !== null || (t.onclick = Da));
    else if (r !== 4 && (e = e.child, e !== null)) for (eu(e, t, n), e = e.sibling; e !== null; ) eu(e, t, n), e = e.sibling;
  }
  function tu(e, t, n) {
    var r = e.tag;
    if (r === 5 || r === 6) e = e.stateNode, t ? n.insertBefore(e, t) : n.appendChild(e);
    else if (r !== 4 && (e = e.child, e !== null)) for (tu(e, t, n), e = e.sibling; e !== null; ) tu(e, t, n), e = e.sibling;
  }
  var ft = null, mn = false;
  function Zn(e, t, n) {
    for (n = n.child; n !== null; ) Ep(e, t, n), n = n.sibling;
  }
  function Ep(e, t, n) {
    if (An && typeof An.onCommitFiberUnmount == "function") try {
      An.onCommitFiberUnmount(es, n);
    } catch {
    }
    switch (n.tag) {
      case 5:
        bt || qr(n, t);
      case 6:
        var r = ft, i = mn;
        ft = null, Zn(e, t, n), ft = r, mn = i, ft !== null && (mn ? (e = ft, n = n.stateNode, e.nodeType === 8 ? e.parentNode.removeChild(n) : e.removeChild(n)) : ft.removeChild(n.stateNode));
        break;
      case 18:
        ft !== null && (mn ? (e = ft, n = n.stateNode, e.nodeType === 8 ? Ms(e.parentNode, n) : e.nodeType === 1 && Ms(e, n), ho(e)) : Ms(ft, n.stateNode));
        break;
      case 4:
        r = ft, i = mn, ft = n.stateNode.containerInfo, mn = true, Zn(e, t, n), ft = r, mn = i;
        break;
      case 0:
      case 11:
      case 14:
      case 15:
        if (!bt && (r = n.updateQueue, r !== null && (r = r.lastEffect, r !== null))) {
          i = r = r.next;
          do {
            var o = i, a = o.destroy;
            o = o.tag, a !== void 0 && (o & 2 || o & 4) && ql(n, t, a), i = i.next;
          } while (i !== r);
        }
        Zn(e, t, n);
        break;
      case 1:
        if (!bt && (qr(n, t), r = n.stateNode, typeof r.componentWillUnmount == "function")) try {
          r.props = n.memoizedProps, r.state = n.memoizedState, r.componentWillUnmount();
        } catch (s) {
          Ye(n, t, s);
        }
        Zn(e, t, n);
        break;
      case 21:
        Zn(e, t, n);
        break;
      case 22:
        n.mode & 1 ? (bt = (r = bt) || n.memoizedState !== null, Zn(e, t, n), bt = r) : Zn(e, t, n);
        break;
      default:
        Zn(e, t, n);
    }
  }
  function _d(e) {
    var t = e.updateQueue;
    if (t !== null) {
      e.updateQueue = null;
      var n = e.stateNode;
      n === null && (n = e.stateNode = new by()), t.forEach(function(r) {
        var i = Fy.bind(null, e, r);
        n.has(r) || (n.add(r), r.then(i, i));
      });
    }
  }
  function dn(e, t) {
    var n = t.deletions;
    if (n !== null) for (var r = 0; r < n.length; r++) {
      var i = n[r];
      try {
        var o = e, a = t, s = a;
        e: for (; s !== null; ) {
          switch (s.tag) {
            case 5:
              ft = s.stateNode, mn = false;
              break e;
            case 3:
              ft = s.stateNode.containerInfo, mn = true;
              break e;
            case 4:
              ft = s.stateNode.containerInfo, mn = true;
              break e;
          }
          s = s.return;
        }
        if (ft === null) throw Error(j(160));
        Ep(o, a, i), ft = null, mn = false;
        var l = i.alternate;
        l !== null && (l.return = null), i.return = null;
      } catch (c) {
        Ye(i, t, c);
      }
    }
    if (t.subtreeFlags & 12854) for (t = t.child; t !== null; ) Sp(t, e), t = t.sibling;
  }
  function Sp(e, t) {
    var n = e.alternate, r = e.flags;
    switch (e.tag) {
      case 0:
      case 11:
      case 14:
      case 15:
        if (dn(t, e), kn(e), r & 4) {
          try {
            ro(3, e, e.return), ls(3, e);
          } catch (b) {
            Ye(e, e.return, b);
          }
          try {
            ro(5, e, e.return);
          } catch (b) {
            Ye(e, e.return, b);
          }
        }
        break;
      case 1:
        dn(t, e), kn(e), r & 512 && n !== null && qr(n, n.return);
        break;
      case 5:
        if (dn(t, e), kn(e), r & 512 && n !== null && qr(n, n.return), e.flags & 32) {
          var i = e.stateNode;
          try {
            lo(i, "");
          } catch (b) {
            Ye(e, e.return, b);
          }
        }
        if (r & 4 && (i = e.stateNode, i != null)) {
          var o = e.memoizedProps, a = n !== null ? n.memoizedProps : o, s = e.type, l = e.updateQueue;
          if (e.updateQueue = null, l !== null) try {
            s === "input" && o.type === "radio" && o.name != null && jf(i, o), Cl(s, a);
            var c = Cl(s, o);
            for (a = 0; a < l.length; a += 2) {
              var h = l[a], f = l[a + 1];
              h === "style" ? Yf(i, f) : h === "dangerouslySetInnerHTML" ? Vf(i, f) : h === "children" ? lo(i, f) : _u(i, h, f, c);
            }
            switch (s) {
              case "input":
                El(i, o);
                break;
              case "textarea":
                Hf(i, o);
                break;
              case "select":
                var p = i._wrapperState.wasMultiple;
                i._wrapperState.wasMultiple = !!o.multiple;
                var y = o.value;
                y != null ? ei(i, !!o.multiple, y, false) : p !== !!o.multiple && (o.defaultValue != null ? ei(i, !!o.multiple, o.defaultValue, true) : ei(i, !!o.multiple, o.multiple ? [] : "", false));
            }
            i[yo] = o;
          } catch (b) {
            Ye(e, e.return, b);
          }
        }
        break;
      case 6:
        if (dn(t, e), kn(e), r & 4) {
          if (e.stateNode === null) throw Error(j(162));
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
          ho(t.containerInfo);
        } catch (b) {
          Ye(e, e.return, b);
        }
        break;
      case 4:
        dn(t, e), kn(e);
        break;
      case 13:
        dn(t, e), kn(e), i = e.child, i.flags & 8192 && (o = i.memoizedState !== null, i.stateNode.isHidden = o, !o || i.alternate !== null && i.alternate.memoizedState !== null || (tc = Ze())), r & 4 && _d(e);
        break;
      case 22:
        if (h = n !== null && n.memoizedState !== null, e.mode & 1 ? (bt = (c = bt) || h, dn(t, e), bt = c) : dn(t, e), kn(e), r & 8192) {
          if (c = e.memoizedState !== null, (e.stateNode.isHidden = c) && !h && e.mode & 1) for (J = e, h = e.child; h !== null; ) {
            for (f = J = h; J !== null; ) {
              switch (p = J, y = p.child, p.tag) {
                case 0:
                case 11:
                case 14:
                case 15:
                  ro(4, p, p.return);
                  break;
                case 1:
                  qr(p, p.return);
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
                  qr(p, p.return);
                  break;
                case 22:
                  if (p.memoizedState !== null) {
                    bd(f);
                    continue;
                  }
              }
              y !== null ? (y.return = p, J = y) : bd(f);
            }
            h = h.sibling;
          }
          e: for (h = null, f = e; ; ) {
            if (f.tag === 5) {
              if (h === null) {
                h = f;
                try {
                  i = f.stateNode, c ? (o = i.style, typeof o.setProperty == "function" ? o.setProperty("display", "none", "important") : o.display = "none") : (s = f.stateNode, l = f.memoizedProps.style, a = l != null && l.hasOwnProperty("display") ? l.display : null, s.style.display = Kf("display", a));
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
        dn(t, e), kn(e), r & 4 && _d(e);
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
            if (wp(n)) {
              var r = n;
              break e;
            }
            n = n.return;
          }
          throw Error(j(160));
        }
        switch (r.tag) {
          case 5:
            var i = r.stateNode;
            r.flags & 32 && (lo(i, ""), r.flags &= -33);
            var o = Sd(e);
            tu(e, o, i);
            break;
          case 3:
          case 4:
            var a = r.stateNode.containerInfo, s = Sd(e);
            eu(e, s, a);
            break;
          default:
            throw Error(j(161));
        }
      } catch (l) {
        Ye(e, e.return, l);
      }
      e.flags &= -3;
    }
    t & 4096 && (e.flags &= -4097);
  }
  function xy(e, t, n) {
    J = e, _p(e);
  }
  function _p(e, t, n) {
    for (var r = (e.mode & 1) !== 0; J !== null; ) {
      var i = J, o = i.child;
      if (i.tag === 22 && r) {
        var a = i.memoizedState !== null || Xo;
        if (!a) {
          var s = i.alternate, l = s !== null && s.memoizedState !== null || bt;
          s = Xo;
          var c = bt;
          if (Xo = a, (bt = l) && !c) for (J = i; J !== null; ) a = J, l = a.child, a.tag === 22 && a.memoizedState !== null ? Cd(i) : l !== null ? (l.return = a, J = l) : Cd(i);
          for (; o !== null; ) J = o, _p(o), o = o.sibling;
          J = i, Xo = s, bt = c;
        }
        kd(e);
      } else i.subtreeFlags & 8772 && o !== null ? (o.return = i, J = o) : kd(e);
    }
  }
  function kd(e) {
    for (; J !== null; ) {
      var t = J;
      if (t.flags & 8772) {
        var n = t.alternate;
        try {
          if (t.flags & 8772) switch (t.tag) {
            case 0:
            case 11:
            case 15:
              bt || ls(5, t);
              break;
            case 1:
              var r = t.stateNode;
              if (t.flags & 4 && !bt) if (n === null) r.componentDidMount();
              else {
                var i = t.elementType === t.type ? n.memoizedProps : gn(t.type, n.memoizedProps);
                r.componentDidUpdate(i, n.memoizedState, r.__reactInternalSnapshotBeforeUpdate);
              }
              var o = t.updateQueue;
              o !== null && sd(t, o, r);
              break;
            case 3:
              var a = t.updateQueue;
              if (a !== null) {
                if (n = null, t.child !== null) switch (t.child.tag) {
                  case 5:
                    n = t.child.stateNode;
                    break;
                  case 1:
                    n = t.child.stateNode;
                }
                sd(t, a, n);
              }
              break;
            case 5:
              var s = t.stateNode;
              if (n === null && t.flags & 4) {
                n = s;
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
                    f !== null && ho(f);
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
              throw Error(j(163));
          }
          bt || t.flags & 512 && Jl(t);
        } catch (p) {
          Ye(t, t.return, p);
        }
      }
      if (t === e) {
        J = null;
        break;
      }
      if (n = t.sibling, n !== null) {
        n.return = t.return, J = n;
        break;
      }
      J = t.return;
    }
  }
  function bd(e) {
    for (; J !== null; ) {
      var t = J;
      if (t === e) {
        J = null;
        break;
      }
      var n = t.sibling;
      if (n !== null) {
        n.return = t.return, J = n;
        break;
      }
      J = t.return;
    }
  }
  function Cd(e) {
    for (; J !== null; ) {
      var t = J;
      try {
        switch (t.tag) {
          case 0:
          case 11:
          case 15:
            var n = t.return;
            try {
              ls(4, t);
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
              Jl(t);
            } catch (l) {
              Ye(t, o, l);
            }
            break;
          case 5:
            var a = t.return;
            try {
              Jl(t);
            } catch (l) {
              Ye(t, a, l);
            }
        }
      } catch (l) {
        Ye(t, t.return, l);
      }
      if (t === e) {
        J = null;
        break;
      }
      var s = t.sibling;
      if (s !== null) {
        s.return = t.return, J = s;
        break;
      }
      J = t.return;
    }
  }
  var Ty = Math.ceil, $a = Kn.ReactCurrentDispatcher, Ju = Kn.ReactCurrentOwner, tn = Kn.ReactCurrentBatchConfig, be = 0, dt = null, Je = null, pt = 0, jt = 0, Jr = yr(0), ot = 0, bo = null, Fr = 0, us = 0, ec = 0, io = null, Ot = null, tc = 0, pi = 1 / 0, zn = null, ja = false, nu = null, fr = null, Zo = false, ar = null, Ha = 0, oo = 0, ru = null, va = -1, ya = 0;
  function Lt() {
    return be & 6 ? Ze() : va !== -1 ? va : va = Ze();
  }
  function hr(e) {
    return e.mode & 1 ? be & 2 && pt !== 0 ? pt & -pt : cy.transition !== null ? (ya === 0 && (ya = ah()), ya) : (e = Pe, e !== 0 || (e = window.event, e = e === void 0 ? 16 : hh(e.type)), e) : 1;
  }
  function En(e, t, n, r) {
    if (50 < oo) throw oo = 0, ru = null, Error(j(185));
    Ro(e, n, r), (!(be & 2) || e !== dt) && (e === dt && (!(be & 2) && (us |= n), ot === 4 && ir(e, pt)), Mt(e, r), n === 1 && be === 0 && !(t.mode & 1) && (pi = Ze() + 500, os && wr()));
  }
  function Mt(e, t) {
    var n = e.callbackNode;
    cv(e, t);
    var r = Ta(e, e === dt ? pt : 0);
    if (r === 0) n !== null && Fc(n), e.callbackNode = null, e.callbackPriority = 0;
    else if (t = r & -r, e.callbackPriority !== t) {
      if (n != null && Fc(n), t === 1) e.tag === 0 ? uy(xd.bind(null, e)) : Ph(xd.bind(null, e)), oy(function() {
        !(be & 6) && wr();
      }), n = null;
      else {
        switch (sh(r)) {
          case 1:
            n = Tu;
            break;
          case 4:
            n = ih;
            break;
          case 16:
            n = xa;
            break;
          case 536870912:
            n = oh;
            break;
          default:
            n = xa;
        }
        n = Lp(n, kp.bind(null, e));
      }
      e.callbackPriority = t, e.callbackNode = n;
    }
  }
  function kp(e, t) {
    if (va = -1, ya = 0, be & 6) throw Error(j(327));
    var n = e.callbackNode;
    if (oi() && e.callbackNode !== n) return null;
    var r = Ta(e, e === dt ? pt : 0);
    if (r === 0) return null;
    if (r & 30 || r & e.expiredLanes || t) t = Wa(e, r);
    else {
      t = r;
      var i = be;
      be |= 2;
      var o = Cp();
      (dt !== e || pt !== t) && (zn = null, pi = Ze() + 500, Ar(e, t));
      do
        try {
          Ly();
          break;
        } catch (s) {
          bp(e, s);
        }
      while (true);
      Bu(), $a.current = o, be = i, Je !== null ? t = 0 : (dt = null, pt = 0, t = ot);
    }
    if (t !== 0) {
      if (t === 2 && (i = Ll(e), i !== 0 && (r = i, t = iu(e, i))), t === 1) throw n = bo, Ar(e, 0), ir(e, r), Mt(e, Ze()), n;
      if (t === 6) ir(e, r);
      else {
        if (i = e.current.alternate, !(r & 30) && !Ry(i) && (t = Wa(e, r), t === 2 && (o = Ll(e), o !== 0 && (r = o, t = iu(e, o))), t === 1)) throw n = bo, Ar(e, 0), ir(e, r), Mt(e, Ze()), n;
        switch (e.finishedWork = i, e.finishedLanes = r, t) {
          case 0:
          case 1:
            throw Error(j(345));
          case 2:
            br(e, Ot, zn);
            break;
          case 3:
            if (ir(e, r), (r & 130023424) === r && (t = tc + 500 - Ze(), 10 < t)) {
              if (Ta(e, 0) !== 0) break;
              if (i = e.suspendedLanes, (i & r) !== r) {
                Lt(), e.pingedLanes |= e.suspendedLanes & i;
                break;
              }
              e.timeoutHandle = Gl(br.bind(null, e, Ot, zn), t);
              break;
            }
            br(e, Ot, zn);
            break;
          case 4:
            if (ir(e, r), (r & 4194240) === r) break;
            for (t = e.eventTimes, i = -1; 0 < r; ) {
              var a = 31 - wn(r);
              o = 1 << a, a = t[a], a > i && (i = a), r &= ~o;
            }
            if (r = i, r = Ze() - r, r = (120 > r ? 120 : 480 > r ? 480 : 1080 > r ? 1080 : 1920 > r ? 1920 : 3e3 > r ? 3e3 : 4320 > r ? 4320 : 1960 * Ty(r / 1960)) - r, 10 < r) {
              e.timeoutHandle = Gl(br.bind(null, e, Ot, zn), r);
              break;
            }
            br(e, Ot, zn);
            break;
          case 5:
            br(e, Ot, zn);
            break;
          default:
            throw Error(j(329));
        }
      }
    }
    return Mt(e, Ze()), e.callbackNode === n ? kp.bind(null, e) : null;
  }
  function iu(e, t) {
    var n = io;
    return e.current.memoizedState.isDehydrated && (Ar(e, t).flags |= 256), e = Wa(e, t), e !== 2 && (t = Ot, Ot = n, t !== null && ou(t)), e;
  }
  function ou(e) {
    Ot === null ? Ot = e : Ot.push.apply(Ot, e);
  }
  function Ry(e) {
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
  function ir(e, t) {
    for (t &= ~ec, t &= ~us, e.suspendedLanes |= t, e.pingedLanes &= ~t, e = e.expirationTimes; 0 < t; ) {
      var n = 31 - wn(t), r = 1 << n;
      e[n] = -1, t &= ~r;
    }
  }
  function xd(e) {
    if (be & 6) throw Error(j(327));
    oi();
    var t = Ta(e, 0);
    if (!(t & 1)) return Mt(e, Ze()), null;
    var n = Wa(e, t);
    if (e.tag !== 0 && n === 2) {
      var r = Ll(e);
      r !== 0 && (t = r, n = iu(e, r));
    }
    if (n === 1) throw n = bo, Ar(e, 0), ir(e, t), Mt(e, Ze()), n;
    if (n === 6) throw Error(j(345));
    return e.finishedWork = e.current.alternate, e.finishedLanes = t, br(e, Ot, zn), Mt(e, Ze()), null;
  }
  function nc(e, t) {
    var n = be;
    be |= 1;
    try {
      return e(t);
    } finally {
      be = n, be === 0 && (pi = Ze() + 500, os && wr());
    }
  }
  function Nr(e) {
    ar !== null && ar.tag === 0 && !(be & 6) && oi();
    var t = be;
    be |= 1;
    var n = tn.transition, r = Pe;
    try {
      if (tn.transition = null, Pe = 1, e) return e();
    } finally {
      Pe = r, tn.transition = n, be = t, !(be & 6) && wr();
    }
  }
  function rc() {
    jt = Jr.current, Ge(Jr);
  }
  function Ar(e, t) {
    e.finishedWork = null, e.finishedLanes = 0;
    var n = e.timeoutHandle;
    if (n !== -1 && (e.timeoutHandle = -1, iy(n)), Je !== null) for (n = Je.return; n !== null; ) {
      var r = n;
      switch (Ou(r), r.tag) {
        case 1:
          r = r.type.childContextTypes, r != null && Pa();
          break;
        case 3:
          fi(), Ge(Ut), Ge(Ct), Vu();
          break;
        case 5:
          Wu(r);
          break;
        case 4:
          fi();
          break;
        case 13:
          Ge(Me);
          break;
        case 19:
          Ge(Me);
          break;
        case 10:
          Mu(r.type._context);
          break;
        case 22:
        case 23:
          rc();
      }
      n = n.return;
    }
    if (dt = e, Je = e = pr(e.current, null), pt = jt = t, ot = 0, bo = null, ec = us = Fr = 0, Ot = io = null, Tr !== null) {
      for (t = 0; t < Tr.length; t++) if (n = Tr[t], r = n.interleaved, r !== null) {
        n.interleaved = null;
        var i = r.next, o = n.pending;
        if (o !== null) {
          var a = o.next;
          o.next = i, r.next = a;
        }
        n.pending = r;
      }
      Tr = null;
    }
    return e;
  }
  function bp(e, t) {
    do {
      var n = Je;
      try {
        if (Bu(), pa.current = Ma, Ba) {
          for (var r = $e.memoizedState; r !== null; ) {
            var i = r.queue;
            i !== null && (i.pending = null), r = r.next;
          }
          Ba = false;
        }
        if (Ir = 0, ct = rt = $e = null, no = false, So = 0, Ju.current = null, n === null || n.return === null) {
          ot = 1, bo = t, Je = null;
          break;
        }
        e: {
          var o = e, a = n.return, s = n, l = t;
          if (t = pt, s.flags |= 32768, l !== null && typeof l == "object" && typeof l.then == "function") {
            var c = l, h = s, f = h.tag;
            if (!(h.mode & 1) && (f === 0 || f === 11 || f === 15)) {
              var p = h.alternate;
              p ? (h.updateQueue = p.updateQueue, h.memoizedState = p.memoizedState, h.lanes = p.lanes) : (h.updateQueue = null, h.memoizedState = null);
            }
            var y = hd(a);
            if (y !== null) {
              y.flags &= -257, pd(y, a, s, o, t), y.mode & 1 && fd(o, c, t), t = y, l = c;
              var k = t.updateQueue;
              if (k === null) {
                var b = /* @__PURE__ */ new Set();
                b.add(l), t.updateQueue = b;
              } else k.add(l);
              break e;
            } else {
              if (!(t & 1)) {
                fd(o, c, t), ic();
                break e;
              }
              l = Error(j(426));
            }
          } else if (Ue && s.mode & 1) {
            var I = hd(a);
            if (I !== null) {
              !(I.flags & 65536) && (I.flags |= 256), pd(I, a, s, o, t), Gu(hi(l, s));
              break e;
            }
          }
          o = l = hi(l, s), ot !== 4 && (ot = 2), io === null ? io = [
            o
          ] : io.push(o), o = a;
          do {
            switch (o.tag) {
              case 3:
                o.flags |= 65536, t &= -t, o.lanes |= t;
                var S = sp(o, l, t);
                ad(o, S);
                break e;
              case 1:
                s = l;
                var m = o.type, v = o.stateNode;
                if (!(o.flags & 128) && (typeof m.getDerivedStateFromError == "function" || v !== null && typeof v.componentDidCatch == "function" && (fr === null || !fr.has(v)))) {
                  o.flags |= 65536, t &= -t, o.lanes |= t;
                  var E = lp(o, s, t);
                  ad(o, E);
                  break e;
                }
            }
            o = o.return;
          } while (o !== null);
        }
        Tp(n);
      } catch (A) {
        t = A, Je === n && n !== null && (Je = n = n.return);
        continue;
      }
      break;
    } while (true);
  }
  function Cp() {
    var e = $a.current;
    return $a.current = Ma, e === null ? Ma : e;
  }
  function ic() {
    (ot === 0 || ot === 3 || ot === 2) && (ot = 4), dt === null || !(Fr & 268435455) && !(us & 268435455) || ir(dt, pt);
  }
  function Wa(e, t) {
    var n = be;
    be |= 2;
    var r = Cp();
    (dt !== e || pt !== t) && (zn = null, Ar(e, t));
    do
      try {
        Ay();
        break;
      } catch (i) {
        bp(e, i);
      }
    while (true);
    if (Bu(), be = n, $a.current = r, Je !== null) throw Error(j(261));
    return dt = null, pt = 0, ot;
  }
  function Ay() {
    for (; Je !== null; ) xp(Je);
  }
  function Ly() {
    for (; Je !== null && !tv(); ) xp(Je);
  }
  function xp(e) {
    var t = Ap(e.alternate, e, jt);
    e.memoizedProps = e.pendingProps, t === null ? Tp(e) : Je = t, Ju.current = null;
  }
  function Tp(e) {
    var t = e;
    do {
      var n = t.alternate;
      if (e = t.return, t.flags & 32768) {
        if (n = ky(n, t), n !== null) {
          n.flags &= 32767, Je = n;
          return;
        }
        if (e !== null) e.flags |= 32768, e.subtreeFlags = 0, e.deletions = null;
        else {
          ot = 6, Je = null;
          return;
        }
      } else if (n = _y(n, t, jt), n !== null) {
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
  function br(e, t, n) {
    var r = Pe, i = tn.transition;
    try {
      tn.transition = null, Pe = 1, Dy(e, t, n, r);
    } finally {
      tn.transition = i, Pe = r;
    }
    return null;
  }
  function Dy(e, t, n, r) {
    do
      oi();
    while (ar !== null);
    if (be & 6) throw Error(j(327));
    n = e.finishedWork;
    var i = e.finishedLanes;
    if (n === null) return null;
    if (e.finishedWork = null, e.finishedLanes = 0, n === e.current) throw Error(j(177));
    e.callbackNode = null, e.callbackPriority = 0;
    var o = n.lanes | n.childLanes;
    if (dv(e, o), e === dt && (Je = dt = null, pt = 0), !(n.subtreeFlags & 2064) && !(n.flags & 2064) || Zo || (Zo = true, Lp(xa, function() {
      return oi(), null;
    })), o = (n.flags & 15990) !== 0, n.subtreeFlags & 15990 || o) {
      o = tn.transition, tn.transition = null;
      var a = Pe;
      Pe = 1;
      var s = be;
      be |= 4, Ju.current = null, Cy(e, n), Sp(n, e), Zv(zl), Ra = !!Nl, zl = Nl = null, e.current = n, xy(n), nv(), be = s, Pe = a, tn.transition = o;
    } else e.current = n;
    if (Zo && (Zo = false, ar = e, Ha = i), o = e.pendingLanes, o === 0 && (fr = null), ov(n.stateNode), Mt(e, Ze()), t !== null) for (r = e.onRecoverableError, n = 0; n < t.length; n++) i = t[n], r(i.value, {
      componentStack: i.stack,
      digest: i.digest
    });
    if (ja) throw ja = false, e = nu, nu = null, e;
    return Ha & 1 && e.tag !== 0 && oi(), o = e.pendingLanes, o & 1 ? e === ru ? oo++ : (oo = 0, ru = e) : oo = 0, wr(), null;
  }
  function oi() {
    if (ar !== null) {
      var e = sh(Ha), t = tn.transition, n = Pe;
      try {
        if (tn.transition = null, Pe = 16 > e ? 16 : e, ar === null) var r = false;
        else {
          if (e = ar, ar = null, Ha = 0, be & 6) throw Error(j(331));
          var i = be;
          for (be |= 4, J = e.current; J !== null; ) {
            var o = J, a = o.child;
            if (J.flags & 16) {
              var s = o.deletions;
              if (s !== null) {
                for (var l = 0; l < s.length; l++) {
                  var c = s[l];
                  for (J = c; J !== null; ) {
                    var h = J;
                    switch (h.tag) {
                      case 0:
                      case 11:
                      case 15:
                        ro(8, h, o);
                    }
                    var f = h.child;
                    if (f !== null) f.return = h, J = f;
                    else for (; J !== null; ) {
                      h = J;
                      var p = h.sibling, y = h.return;
                      if (yp(h), h === c) {
                        J = null;
                        break;
                      }
                      if (p !== null) {
                        p.return = y, J = p;
                        break;
                      }
                      J = y;
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
                J = o;
              }
            }
            if (o.subtreeFlags & 2064 && a !== null) a.return = o, J = a;
            else e: for (; J !== null; ) {
              if (o = J, o.flags & 2048) switch (o.tag) {
                case 0:
                case 11:
                case 15:
                  ro(9, o, o.return);
              }
              var S = o.sibling;
              if (S !== null) {
                S.return = o.return, J = S;
                break e;
              }
              J = o.return;
            }
          }
          var m = e.current;
          for (J = m; J !== null; ) {
            a = J;
            var v = a.child;
            if (a.subtreeFlags & 2064 && v !== null) v.return = a, J = v;
            else e: for (a = m; J !== null; ) {
              if (s = J, s.flags & 2048) try {
                switch (s.tag) {
                  case 0:
                  case 11:
                  case 15:
                    ls(9, s);
                }
              } catch (A) {
                Ye(s, s.return, A);
              }
              if (s === a) {
                J = null;
                break e;
              }
              var E = s.sibling;
              if (E !== null) {
                E.return = s.return, J = E;
                break e;
              }
              J = s.return;
            }
          }
          if (be = i, wr(), An && typeof An.onPostCommitFiberRoot == "function") try {
            An.onPostCommitFiberRoot(es, e);
          } catch {
          }
          r = true;
        }
        return r;
      } finally {
        Pe = n, tn.transition = t;
      }
    }
    return false;
  }
  function Td(e, t, n) {
    t = hi(n, t), t = sp(e, t, 1), e = dr(e, t, 1), t = Lt(), e !== null && (Ro(e, 1, t), Mt(e, t));
  }
  function Ye(e, t, n) {
    if (e.tag === 3) Td(e, e, n);
    else for (; t !== null; ) {
      if (t.tag === 3) {
        Td(t, e, n);
        break;
      } else if (t.tag === 1) {
        var r = t.stateNode;
        if (typeof t.type.getDerivedStateFromError == "function" || typeof r.componentDidCatch == "function" && (fr === null || !fr.has(r))) {
          e = hi(n, e), e = lp(t, e, 1), t = dr(t, e, 1), e = Lt(), t !== null && (Ro(t, 1, e), Mt(t, e));
          break;
        }
      }
      t = t.return;
    }
  }
  function Py(e, t, n) {
    var r = e.pingCache;
    r !== null && r.delete(t), t = Lt(), e.pingedLanes |= e.suspendedLanes & n, dt === e && (pt & n) === n && (ot === 4 || ot === 3 && (pt & 130023424) === pt && 500 > Ze() - tc ? Ar(e, 0) : ec |= n), Mt(e, t);
  }
  function Rp(e, t) {
    t === 0 && (e.mode & 1 ? (t = Mo, Mo <<= 1, !(Mo & 130023424) && (Mo = 4194304)) : t = 1);
    var n = Lt();
    e = Wn(e, t), e !== null && (Ro(e, t, n), Mt(e, n));
  }
  function Iy(e) {
    var t = e.memoizedState, n = 0;
    t !== null && (n = t.retryLane), Rp(e, n);
  }
  function Fy(e, t) {
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
        throw Error(j(314));
    }
    r !== null && r.delete(t), Rp(e, n);
  }
  var Ap;
  Ap = function(e, t, n) {
    if (e !== null) if (e.memoizedProps !== t.pendingProps || Ut.current) Gt = true;
    else {
      if (!(e.lanes & n) && !(t.flags & 128)) return Gt = false, Sy(e, t, n);
      Gt = !!(e.flags & 131072);
    }
    else Gt = false, Ue && t.flags & 1048576 && Ih(t, Na, t.index);
    switch (t.lanes = 0, t.tag) {
      case 2:
        var r = t.type;
        ma(e, t), e = t.pendingProps;
        var i = ui(t, Ct.current);
        ii(t, n), i = Yu(null, t, r, e, i, n);
        var o = Qu();
        return t.flags |= 1, typeof i == "object" && i !== null && typeof i.render == "function" && i.$$typeof === void 0 ? (t.tag = 1, t.memoizedState = null, t.updateQueue = null, Bt(r) ? (o = true, Ia(t)) : o = false, t.memoizedState = i.state !== null && i.state !== void 0 ? i.state : null, ju(t), i.updater = ss, t.stateNode = i, i._reactInternals = t, Wl(t, r, e, n), t = Yl(null, t, r, true, o, n)) : (t.tag = 0, Ue && o && zu(t), At(null, t, i, n), t = t.child), t;
      case 16:
        r = t.elementType;
        e: {
          switch (ma(e, t), e = t.pendingProps, i = r._init, r = i(r._payload), t.type = r, i = t.tag = zy(r), e = gn(r, e), i) {
            case 0:
              t = Kl(null, t, r, e, n);
              break e;
            case 1:
              t = vd(null, t, r, e, n);
              break e;
            case 11:
              t = gd(null, t, r, e, n);
              break e;
            case 14:
              t = md(null, t, r, gn(r.type, e), n);
              break e;
          }
          throw Error(j(306, r, ""));
        }
        return t;
      case 0:
        return r = t.type, i = t.pendingProps, i = t.elementType === r ? i : gn(r, i), Kl(e, t, r, i, n);
      case 1:
        return r = t.type, i = t.pendingProps, i = t.elementType === r ? i : gn(r, i), vd(e, t, r, i, n);
      case 3:
        e: {
          if (fp(t), e === null) throw Error(j(387));
          r = t.pendingProps, o = t.memoizedState, i = o.element, Uh(e, t), Ga(t, r, null, n);
          var a = t.memoizedState;
          if (r = a.element, o.isDehydrated) if (o = {
            element: r,
            isDehydrated: false,
            cache: a.cache,
            pendingSuspenseBoundaries: a.pendingSuspenseBoundaries,
            transitions: a.transitions
          }, t.updateQueue.baseState = o, t.memoizedState = o, t.flags & 256) {
            i = hi(Error(j(423)), t), t = yd(e, t, r, n, i);
            break e;
          } else if (r !== i) {
            i = hi(Error(j(424)), t), t = yd(e, t, r, n, i);
            break e;
          } else for (Ht = cr(t.stateNode.containerInfo.firstChild), Wt = t, Ue = true, vn = null, n = Oh(t, null, r, n), t.child = n; n; ) n.flags = n.flags & -3 | 4096, n = n.sibling;
          else {
            if (ci(), r === i) {
              t = Vn(e, t, n);
              break e;
            }
            At(e, t, r, n);
          }
          t = t.child;
        }
        return t;
      case 5:
        return Bh(t), e === null && $l(t), r = t.type, i = t.pendingProps, o = e !== null ? e.memoizedProps : null, a = i.children, Ol(r, i) ? a = null : o !== null && Ol(r, o) && (t.flags |= 32), dp(e, t), At(e, t, a, n), t.child;
      case 6:
        return e === null && $l(t), null;
      case 13:
        return hp(e, t, n);
      case 4:
        return Hu(t, t.stateNode.containerInfo), r = t.pendingProps, e === null ? t.child = di(t, null, r, n) : At(e, t, r, n), t.child;
      case 11:
        return r = t.type, i = t.pendingProps, i = t.elementType === r ? i : gn(r, i), gd(e, t, r, i, n);
      case 7:
        return At(e, t, t.pendingProps, n), t.child;
      case 8:
        return At(e, t, t.pendingProps.children, n), t.child;
      case 12:
        return At(e, t, t.pendingProps.children, n), t.child;
      case 10:
        e: {
          if (r = t.type._context, i = t.pendingProps, o = t.memoizedProps, a = i.value, Ne(za, r._currentValue), r._currentValue = a, o !== null) if (Sn(o.value, a)) {
            if (o.children === i.children && !Ut.current) {
              t = Vn(e, t, n);
              break e;
            }
          } else for (o = t.child, o !== null && (o.return = t); o !== null; ) {
            var s = o.dependencies;
            if (s !== null) {
              a = o.child;
              for (var l = s.firstContext; l !== null; ) {
                if (l.context === r) {
                  if (o.tag === 1) {
                    l = Mn(-1, n & -n), l.tag = 2;
                    var c = o.updateQueue;
                    if (c !== null) {
                      c = c.shared;
                      var h = c.pending;
                      h === null ? l.next = l : (l.next = h.next, h.next = l), c.pending = l;
                    }
                  }
                  o.lanes |= n, l = o.alternate, l !== null && (l.lanes |= n), jl(o.return, n, t), s.lanes |= n;
                  break;
                }
                l = l.next;
              }
            } else if (o.tag === 10) a = o.type === t.type ? null : o.child;
            else if (o.tag === 18) {
              if (a = o.return, a === null) throw Error(j(341));
              a.lanes |= n, s = a.alternate, s !== null && (s.lanes |= n), jl(a, n, t), a = o.sibling;
            } else a = o.child;
            if (a !== null) a.return = o;
            else for (a = o; a !== null; ) {
              if (a === t) {
                a = null;
                break;
              }
              if (o = a.sibling, o !== null) {
                o.return = a.return, a = o;
                break;
              }
              a = a.return;
            }
            o = a;
          }
          At(e, t, i.children, n), t = t.child;
        }
        return t;
      case 9:
        return i = t.type, r = t.pendingProps.children, ii(t, n), i = rn(i), r = r(i), t.flags |= 1, At(e, t, r, n), t.child;
      case 14:
        return r = t.type, i = gn(r, t.pendingProps), i = gn(r.type, i), md(e, t, r, i, n);
      case 15:
        return up(e, t, t.type, t.pendingProps, n);
      case 17:
        return r = t.type, i = t.pendingProps, i = t.elementType === r ? i : gn(r, i), ma(e, t), t.tag = 1, Bt(r) ? (e = true, Ia(t)) : e = false, ii(t, n), ap(t, r, i), Wl(t, r, i, n), Yl(null, t, r, true, e, n);
      case 19:
        return pp(e, t, n);
      case 22:
        return cp(e, t, n);
    }
    throw Error(j(156, t.tag));
  };
  function Lp(e, t) {
    return rh(e, t);
  }
  function Ny(e, t, n, r) {
    this.tag = e, this.key = n, this.sibling = this.child = this.return = this.stateNode = this.type = this.elementType = null, this.index = 0, this.ref = null, this.pendingProps = t, this.dependencies = this.memoizedState = this.updateQueue = this.memoizedProps = null, this.mode = r, this.subtreeFlags = this.flags = 0, this.deletions = null, this.childLanes = this.lanes = 0, this.alternate = null;
  }
  function en(e, t, n, r) {
    return new Ny(e, t, n, r);
  }
  function oc(e) {
    return e = e.prototype, !(!e || !e.isReactComponent);
  }
  function zy(e) {
    if (typeof e == "function") return oc(e) ? 1 : 0;
    if (e != null) {
      if (e = e.$$typeof, e === bu) return 11;
      if (e === Cu) return 14;
    }
    return 2;
  }
  function pr(e, t) {
    var n = e.alternate;
    return n === null ? (n = en(e.tag, t, e.key, e.mode), n.elementType = e.elementType, n.type = e.type, n.stateNode = e.stateNode, n.alternate = e, e.alternate = n) : (n.pendingProps = t, n.type = e.type, n.flags = 0, n.subtreeFlags = 0, n.deletions = null), n.flags = e.flags & 14680064, n.childLanes = e.childLanes, n.lanes = e.lanes, n.child = e.child, n.memoizedProps = e.memoizedProps, n.memoizedState = e.memoizedState, n.updateQueue = e.updateQueue, t = e.dependencies, n.dependencies = t === null ? null : {
      lanes: t.lanes,
      firstContext: t.firstContext
    }, n.sibling = e.sibling, n.index = e.index, n.ref = e.ref, n;
  }
  function wa(e, t, n, r, i, o) {
    var a = 2;
    if (r = e, typeof e == "function") oc(e) && (a = 1);
    else if (typeof e == "string") a = 5;
    else e: switch (e) {
      case jr:
        return Lr(n.children, i, o, t);
      case ku:
        a = 8, i |= 8;
        break;
      case gl:
        return e = en(12, n, t, i | 2), e.elementType = gl, e.lanes = o, e;
      case ml:
        return e = en(13, n, t, i), e.elementType = ml, e.lanes = o, e;
      case vl:
        return e = en(19, n, t, i), e.elementType = vl, e.lanes = o, e;
      case Bf:
        return cs(n, i, o, t);
      default:
        if (typeof e == "object" && e !== null) switch (e.$$typeof) {
          case Gf:
            a = 10;
            break e;
          case Uf:
            a = 9;
            break e;
          case bu:
            a = 11;
            break e;
          case Cu:
            a = 14;
            break e;
          case tr:
            a = 16, r = null;
            break e;
        }
        throw Error(j(130, e == null ? e : typeof e, ""));
    }
    return t = en(a, n, t, i), t.elementType = e, t.type = r, t.lanes = o, t;
  }
  function Lr(e, t, n, r) {
    return e = en(7, e, r, t), e.lanes = n, e;
  }
  function cs(e, t, n, r) {
    return e = en(22, e, r, t), e.elementType = Bf, e.lanes = n, e.stateNode = {
      isHidden: false
    }, e;
  }
  function Qs(e, t, n) {
    return e = en(6, e, null, t), e.lanes = n, e;
  }
  function Xs(e, t, n) {
    return t = en(4, e.children !== null ? e.children : [], e.key, t), t.lanes = n, t.stateNode = {
      containerInfo: e.containerInfo,
      pendingChildren: null,
      implementation: e.implementation
    }, t;
  }
  function Oy(e, t, n, r, i) {
    this.tag = t, this.containerInfo = e, this.finishedWork = this.pingCache = this.current = this.pendingChildren = null, this.timeoutHandle = -1, this.callbackNode = this.pendingContext = this.context = null, this.callbackPriority = 0, this.eventTimes = Ls(0), this.expirationTimes = Ls(-1), this.entangledLanes = this.finishedLanes = this.mutableReadLanes = this.expiredLanes = this.pingedLanes = this.suspendedLanes = this.pendingLanes = 0, this.entanglements = Ls(0), this.identifierPrefix = r, this.onRecoverableError = i, this.mutableSourceEagerHydrationData = null;
  }
  function ac(e, t, n, r, i, o, a, s, l) {
    return e = new Oy(e, t, n, s, l), t === 1 ? (t = 1, o === true && (t |= 8)) : t = 0, o = en(3, null, null, t), e.current = o, o.stateNode = e, o.memoizedState = {
      element: r,
      isDehydrated: n,
      cache: null,
      transitions: null,
      pendingSuspenseBoundaries: null
    }, ju(o), e;
  }
  function Gy(e, t, n) {
    var r = 3 < arguments.length && arguments[3] !== void 0 ? arguments[3] : null;
    return {
      $$typeof: $r,
      key: r == null ? null : "" + r,
      children: e,
      containerInfo: t,
      implementation: n
    };
  }
  function Dp(e) {
    if (!e) return mr;
    e = e._reactInternals;
    e: {
      if (Or(e) !== e || e.tag !== 1) throw Error(j(170));
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
      throw Error(j(171));
    }
    if (e.tag === 1) {
      var n = e.type;
      if (Bt(n)) return Dh(e, n, t);
    }
    return t;
  }
  function Pp(e, t, n, r, i, o, a, s, l) {
    return e = ac(n, r, true, e, i, o, a, s, l), e.context = Dp(null), n = e.current, r = Lt(), i = hr(n), o = Mn(r, i), o.callback = t ?? null, dr(n, o, i), e.current.lanes = i, Ro(e, i, r), Mt(e, r), e;
  }
  function ds(e, t, n, r) {
    var i = t.current, o = Lt(), a = hr(i);
    return n = Dp(n), t.context === null ? t.context = n : t.pendingContext = n, t = Mn(o, a), t.payload = {
      element: e
    }, r = r === void 0 ? null : r, r !== null && (t.callback = r), e = dr(i, t, a), e !== null && (En(e, i, a, o), ha(e, i, a)), a;
  }
  function Va(e) {
    if (e = e.current, !e.child) return null;
    switch (e.child.tag) {
      case 5:
        return e.child.stateNode;
      default:
        return e.child.stateNode;
    }
  }
  function Rd(e, t) {
    if (e = e.memoizedState, e !== null && e.dehydrated !== null) {
      var n = e.retryLane;
      e.retryLane = n !== 0 && n < t ? n : t;
    }
  }
  function sc(e, t) {
    Rd(e, t), (e = e.alternate) && Rd(e, t);
  }
  function Uy() {
    return null;
  }
  var Ip = typeof reportError == "function" ? reportError : function(e) {
    console.error(e);
  };
  function lc(e) {
    this._internalRoot = e;
  }
  fs.prototype.render = lc.prototype.render = function(e) {
    var t = this._internalRoot;
    if (t === null) throw Error(j(409));
    ds(e, t, null, null);
  };
  fs.prototype.unmount = lc.prototype.unmount = function() {
    var e = this._internalRoot;
    if (e !== null) {
      this._internalRoot = null;
      var t = e.containerInfo;
      Nr(function() {
        ds(null, e, null, null);
      }), t[Hn] = null;
    }
  };
  function fs(e) {
    this._internalRoot = e;
  }
  fs.prototype.unstable_scheduleHydration = function(e) {
    if (e) {
      var t = ch();
      e = {
        blockedOn: null,
        target: e,
        priority: t
      };
      for (var n = 0; n < rr.length && t !== 0 && t < rr[n].priority; n++) ;
      rr.splice(n, 0, e), n === 0 && fh(e);
    }
  };
  function uc(e) {
    return !(!e || e.nodeType !== 1 && e.nodeType !== 9 && e.nodeType !== 11);
  }
  function hs(e) {
    return !(!e || e.nodeType !== 1 && e.nodeType !== 9 && e.nodeType !== 11 && (e.nodeType !== 8 || e.nodeValue !== " react-mount-point-unstable "));
  }
  function Ad() {
  }
  function By(e, t, n, r, i) {
    if (i) {
      if (typeof r == "function") {
        var o = r;
        r = function() {
          var c = Va(a);
          o.call(c);
        };
      }
      var a = Pp(t, r, e, 0, null, false, false, "", Ad);
      return e._reactRootContainer = a, e[Hn] = a.current, mo(e.nodeType === 8 ? e.parentNode : e), Nr(), a;
    }
    for (; i = e.lastChild; ) e.removeChild(i);
    if (typeof r == "function") {
      var s = r;
      r = function() {
        var c = Va(l);
        s.call(c);
      };
    }
    var l = ac(e, 0, false, null, null, false, false, "", Ad);
    return e._reactRootContainer = l, e[Hn] = l.current, mo(e.nodeType === 8 ? e.parentNode : e), Nr(function() {
      ds(t, l, n, r);
    }), l;
  }
  function ps(e, t, n, r, i) {
    var o = n._reactRootContainer;
    if (o) {
      var a = o;
      if (typeof i == "function") {
        var s = i;
        i = function() {
          var l = Va(a);
          s.call(l);
        };
      }
      ds(t, a, e, i);
    } else a = By(n, t, e, i, r);
    return Va(a);
  }
  lh = function(e) {
    switch (e.tag) {
      case 3:
        var t = e.stateNode;
        if (t.current.memoizedState.isDehydrated) {
          var n = Yi(t.pendingLanes);
          n !== 0 && (Ru(t, n | 1), Mt(t, Ze()), !(be & 6) && (pi = Ze() + 500, wr()));
        }
        break;
      case 13:
        Nr(function() {
          var r = Wn(e, 1);
          if (r !== null) {
            var i = Lt();
            En(r, e, 1, i);
          }
        }), sc(e, 1);
    }
  };
  Au = function(e) {
    if (e.tag === 13) {
      var t = Wn(e, 134217728);
      if (t !== null) {
        var n = Lt();
        En(t, e, 134217728, n);
      }
      sc(e, 134217728);
    }
  };
  uh = function(e) {
    if (e.tag === 13) {
      var t = hr(e), n = Wn(e, t);
      if (n !== null) {
        var r = Lt();
        En(n, e, t, r);
      }
      sc(e, t);
    }
  };
  ch = function() {
    return Pe;
  };
  dh = function(e, t) {
    var n = Pe;
    try {
      return Pe = e, t();
    } finally {
      Pe = n;
    }
  };
  Tl = function(e, t, n) {
    switch (t) {
      case "input":
        if (El(e, n), t = n.name, n.type === "radio" && t != null) {
          for (n = e; n.parentNode; ) n = n.parentNode;
          for (n = n.querySelectorAll("input[name=" + JSON.stringify("" + t) + '][type="radio"]'), t = 0; t < n.length; t++) {
            var r = n[t];
            if (r !== e && r.form === e.form) {
              var i = is(r);
              if (!i) throw Error(j(90));
              $f(r), El(r, i);
            }
          }
        }
        break;
      case "textarea":
        Hf(e, n);
        break;
      case "select":
        t = n.value, t != null && ei(e, !!n.multiple, t, false);
    }
  };
  Zf = nc;
  qf = Nr;
  var My = {
    usingClientEntryPoint: false,
    Events: [
      Lo,
      Kr,
      is,
      Qf,
      Xf,
      nc
    ]
  }, Ni = {
    findFiberByHostInstance: xr,
    bundleType: 0,
    version: "18.3.1",
    rendererPackageName: "react-dom"
  }, $y = {
    bundleType: Ni.bundleType,
    version: Ni.version,
    rendererPackageName: Ni.rendererPackageName,
    rendererConfig: Ni.rendererConfig,
    overrideHookState: null,
    overrideHookStateDeletePath: null,
    overrideHookStateRenamePath: null,
    overrideProps: null,
    overridePropsDeletePath: null,
    overridePropsRenamePath: null,
    setErrorHandler: null,
    setSuspenseHandler: null,
    scheduleUpdate: null,
    currentDispatcherRef: Kn.ReactCurrentDispatcher,
    findHostInstanceByFiber: function(e) {
      return e = th(e), e === null ? null : e.stateNode;
    },
    findFiberByHostInstance: Ni.findFiberByHostInstance || Uy,
    findHostInstancesForRefresh: null,
    scheduleRefresh: null,
    scheduleRoot: null,
    setRefreshHandler: null,
    getCurrentFiber: null,
    reconcilerVersion: "18.3.1-next-f1338f8080-20240426"
  };
  if (typeof __REACT_DEVTOOLS_GLOBAL_HOOK__ < "u") {
    var qo = __REACT_DEVTOOLS_GLOBAL_HOOK__;
    if (!qo.isDisabled && qo.supportsFiber) try {
      es = qo.inject($y), An = qo;
    } catch {
    }
  }
  Kt.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED = My;
  Kt.createPortal = function(e, t) {
    var n = 2 < arguments.length && arguments[2] !== void 0 ? arguments[2] : null;
    if (!uc(t)) throw Error(j(200));
    return Gy(e, t, null, n);
  };
  Kt.createRoot = function(e, t) {
    if (!uc(e)) throw Error(j(299));
    var n = false, r = "", i = Ip;
    return t != null && (t.unstable_strictMode === true && (n = true), t.identifierPrefix !== void 0 && (r = t.identifierPrefix), t.onRecoverableError !== void 0 && (i = t.onRecoverableError)), t = ac(e, 1, false, null, null, n, false, r, i), e[Hn] = t.current, mo(e.nodeType === 8 ? e.parentNode : e), new lc(t);
  };
  Kt.findDOMNode = function(e) {
    if (e == null) return null;
    if (e.nodeType === 1) return e;
    var t = e._reactInternals;
    if (t === void 0) throw typeof e.render == "function" ? Error(j(188)) : (e = Object.keys(e).join(","), Error(j(268, e)));
    return e = th(t), e = e === null ? null : e.stateNode, e;
  };
  Kt.flushSync = function(e) {
    return Nr(e);
  };
  Kt.hydrate = function(e, t, n) {
    if (!hs(t)) throw Error(j(200));
    return ps(null, e, t, true, n);
  };
  Kt.hydrateRoot = function(e, t, n) {
    if (!uc(e)) throw Error(j(405));
    var r = n != null && n.hydratedSources || null, i = false, o = "", a = Ip;
    if (n != null && (n.unstable_strictMode === true && (i = true), n.identifierPrefix !== void 0 && (o = n.identifierPrefix), n.onRecoverableError !== void 0 && (a = n.onRecoverableError)), t = Pp(t, null, e, 1, n ?? null, i, false, o, a), e[Hn] = t.current, mo(e), r) for (e = 0; e < r.length; e++) n = r[e], i = n._getVersion, i = i(n._source), t.mutableSourceEagerHydrationData == null ? t.mutableSourceEagerHydrationData = [
      n,
      i
    ] : t.mutableSourceEagerHydrationData.push(n, i);
    return new fs(t);
  };
  Kt.render = function(e, t, n) {
    if (!hs(t)) throw Error(j(200));
    return ps(null, e, t, false, n);
  };
  Kt.unmountComponentAtNode = function(e) {
    if (!hs(e)) throw Error(j(40));
    return e._reactRootContainer ? (Nr(function() {
      ps(null, null, e, false, function() {
        e._reactRootContainer = null, e[Hn] = null;
      });
    }), true) : false;
  };
  Kt.unstable_batchedUpdates = nc;
  Kt.unstable_renderSubtreeIntoContainer = function(e, t, n, r) {
    if (!hs(n)) throw Error(j(200));
    if (e == null || e._reactInternals === void 0) throw Error(j(38));
    return ps(e, t, n, false, r);
  };
  Kt.version = "18.3.1-next-f1338f8080-20240426";
  function Fp() {
    if (!(typeof __REACT_DEVTOOLS_GLOBAL_HOOK__ > "u" || typeof __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE != "function")) try {
      __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE(Fp);
    } catch (e) {
      console.error(e);
    }
  }
  Fp(), Ff.exports = Kt;
  var jy = Ff.exports, Ld = jy;
  hl.createRoot = Ld.createRoot, hl.hydrateRoot = Ld.hydrateRoot;
  var Np = {}, gs = {};
  gs.byteLength = Vy;
  gs.toByteArray = Yy;
  gs.fromByteArray = Zy;
  var Rn = [], Zt = [], Hy = typeof Uint8Array < "u" ? Uint8Array : Array, Zs = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  for (var Ur = 0, Wy = Zs.length; Ur < Wy; ++Ur) Rn[Ur] = Zs[Ur], Zt[Zs.charCodeAt(Ur)] = Ur;
  Zt[45] = 62;
  Zt[95] = 63;
  function zp(e) {
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
  function Vy(e) {
    var t = zp(e), n = t[0], r = t[1];
    return (n + r) * 3 / 4 - r;
  }
  function Ky(e, t, n) {
    return (t + n) * 3 / 4 - n;
  }
  function Yy(e) {
    var t, n = zp(e), r = n[0], i = n[1], o = new Hy(Ky(e, r, i)), a = 0, s = i > 0 ? r - 4 : r, l;
    for (l = 0; l < s; l += 4) t = Zt[e.charCodeAt(l)] << 18 | Zt[e.charCodeAt(l + 1)] << 12 | Zt[e.charCodeAt(l + 2)] << 6 | Zt[e.charCodeAt(l + 3)], o[a++] = t >> 16 & 255, o[a++] = t >> 8 & 255, o[a++] = t & 255;
    return i === 2 && (t = Zt[e.charCodeAt(l)] << 2 | Zt[e.charCodeAt(l + 1)] >> 4, o[a++] = t & 255), i === 1 && (t = Zt[e.charCodeAt(l)] << 10 | Zt[e.charCodeAt(l + 1)] << 4 | Zt[e.charCodeAt(l + 2)] >> 2, o[a++] = t >> 8 & 255, o[a++] = t & 255), o;
  }
  function Qy(e) {
    return Rn[e >> 18 & 63] + Rn[e >> 12 & 63] + Rn[e >> 6 & 63] + Rn[e & 63];
  }
  function Xy(e, t, n) {
    for (var r, i = [], o = t; o < n; o += 3) r = (e[o] << 16 & 16711680) + (e[o + 1] << 8 & 65280) + (e[o + 2] & 255), i.push(Qy(r));
    return i.join("");
  }
  function Zy(e) {
    for (var t, n = e.length, r = n % 3, i = [], o = 16383, a = 0, s = n - r; a < s; a += o) i.push(Xy(e, a, a + o > s ? s : a + o));
    return r === 1 ? (t = e[n - 1], i.push(Rn[t >> 2] + Rn[t << 4 & 63] + "==")) : r === 2 && (t = (e[n - 2] << 8) + e[n - 1], i.push(Rn[t >> 10] + Rn[t >> 4 & 63] + Rn[t << 2 & 63] + "=")), i.join("");
  }
  var cc = {};
  cc.read = function(e, t, n, r, i) {
    var o, a, s = i * 8 - r - 1, l = (1 << s) - 1, c = l >> 1, h = -7, f = n ? i - 1 : 0, p = n ? -1 : 1, y = e[t + f];
    for (f += p, o = y & (1 << -h) - 1, y >>= -h, h += s; h > 0; o = o * 256 + e[t + f], f += p, h -= 8) ;
    for (a = o & (1 << -h) - 1, o >>= -h, h += r; h > 0; a = a * 256 + e[t + f], f += p, h -= 8) ;
    if (o === 0) o = 1 - c;
    else {
      if (o === l) return a ? NaN : (y ? -1 : 1) * (1 / 0);
      a = a + Math.pow(2, r), o = o - c;
    }
    return (y ? -1 : 1) * a * Math.pow(2, o - r);
  };
  cc.write = function(e, t, n, r, i, o) {
    var a, s, l, c = o * 8 - i - 1, h = (1 << c) - 1, f = h >> 1, p = i === 23 ? Math.pow(2, -24) - Math.pow(2, -77) : 0, y = r ? 0 : o - 1, k = r ? 1 : -1, b = t < 0 || t === 0 && 1 / t < 0 ? 1 : 0;
    for (t = Math.abs(t), isNaN(t) || t === 1 / 0 ? (s = isNaN(t) ? 1 : 0, a = h) : (a = Math.floor(Math.log(t) / Math.LN2), t * (l = Math.pow(2, -a)) < 1 && (a--, l *= 2), a + f >= 1 ? t += p / l : t += p * Math.pow(2, 1 - f), t * l >= 2 && (a++, l /= 2), a + f >= h ? (s = 0, a = h) : a + f >= 1 ? (s = (t * l - 1) * Math.pow(2, i), a = a + f) : (s = t * Math.pow(2, f - 1) * Math.pow(2, i), a = 0)); i >= 8; e[n + y] = s & 255, y += k, s /= 256, i -= 8) ;
    for (a = a << i | s, c += i; c > 0; e[n + y] = a & 255, y += k, a /= 256, c -= 8) ;
    e[n + y - k] |= b * 128;
  };
  (function(e) {
    const t = gs, n = cc, r = typeof Symbol == "function" && typeof Symbol.for == "function" ? Symbol.for("nodejs.util.inspect.custom") : null;
    e.Buffer = s, e.SlowBuffer = m, e.INSPECT_MAX_BYTES = 50;
    const i = 2147483647;
    e.kMaxLength = i, s.TYPED_ARRAY_SUPPORT = o(), !s.TYPED_ARRAY_SUPPORT && typeof console < "u" && typeof console.error == "function" && console.error("This browser lacks typed array (Uint8Array) support which is required by `buffer` v5.x. Use `buffer` v4.x if you require old browser support.");
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
    Object.defineProperty(s.prototype, "parent", {
      enumerable: true,
      get: function() {
        if (s.isBuffer(this)) return this.buffer;
      }
    }), Object.defineProperty(s.prototype, "offset", {
      enumerable: true,
      get: function() {
        if (s.isBuffer(this)) return this.byteOffset;
      }
    });
    function a(g) {
      if (g > i) throw new RangeError('The value "' + g + '" is invalid for option "size"');
      const u = new Uint8Array(g);
      return Object.setPrototypeOf(u, s.prototype), u;
    }
    function s(g, u, d) {
      if (typeof g == "number") {
        if (typeof u == "string") throw new TypeError('The "string" argument must be of type string. Received type number');
        return f(g);
      }
      return l(g, u, d);
    }
    s.poolSize = 8192;
    function l(g, u, d) {
      if (typeof g == "string") return p(g, u);
      if (ArrayBuffer.isView(g)) return k(g);
      if (g == null) throw new TypeError("The first argument must be one of type string, Buffer, ArrayBuffer, Array, or Array-like Object. Received type " + typeof g);
      if (He(g, ArrayBuffer) || g && He(g.buffer, ArrayBuffer) || typeof SharedArrayBuffer < "u" && (He(g, SharedArrayBuffer) || g && He(g.buffer, SharedArrayBuffer))) return b(g, u, d);
      if (typeof g == "number") throw new TypeError('The "value" argument must not be of type number. Received type number');
      const w = g.valueOf && g.valueOf();
      if (w != null && w !== g) return s.from(w, u, d);
      const T = I(g);
      if (T) return T;
      if (typeof Symbol < "u" && Symbol.toPrimitive != null && typeof g[Symbol.toPrimitive] == "function") return s.from(g[Symbol.toPrimitive]("string"), u, d);
      throw new TypeError("The first argument must be one of type string, Buffer, ArrayBuffer, Array, or Array-like Object. Received type " + typeof g);
    }
    s.from = function(g, u, d) {
      return l(g, u, d);
    }, Object.setPrototypeOf(s.prototype, Uint8Array.prototype), Object.setPrototypeOf(s, Uint8Array);
    function c(g) {
      if (typeof g != "number") throw new TypeError('"size" argument must be of type number');
      if (g < 0) throw new RangeError('The value "' + g + '" is invalid for option "size"');
    }
    function h(g, u, d) {
      return c(g), g <= 0 ? a(g) : u !== void 0 ? typeof d == "string" ? a(g).fill(u, d) : a(g).fill(u) : a(g);
    }
    s.alloc = function(g, u, d) {
      return h(g, u, d);
    };
    function f(g) {
      return c(g), a(g < 0 ? 0 : S(g) | 0);
    }
    s.allocUnsafe = function(g) {
      return f(g);
    }, s.allocUnsafeSlow = function(g) {
      return f(g);
    };
    function p(g, u) {
      if ((typeof u != "string" || u === "") && (u = "utf8"), !s.isEncoding(u)) throw new TypeError("Unknown encoding: " + u);
      const d = v(g, u) | 0;
      let w = a(d);
      const T = w.write(g, u);
      return T !== d && (w = w.slice(0, T)), w;
    }
    function y(g) {
      const u = g.length < 0 ? 0 : S(g.length) | 0, d = a(u);
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
      return u === void 0 && d === void 0 ? w = new Uint8Array(g) : d === void 0 ? w = new Uint8Array(g, u) : w = new Uint8Array(g, u, d), Object.setPrototypeOf(w, s.prototype), w;
    }
    function I(g) {
      if (s.isBuffer(g)) {
        const u = S(g.length) | 0, d = a(u);
        return d.length === 0 || g.copy(d, 0, 0, u), d;
      }
      if (g.length !== void 0) return typeof g.length != "number" || It(g.length) ? a(0) : y(g);
      if (g.type === "Buffer" && Array.isArray(g.data)) return y(g.data);
    }
    function S(g) {
      if (g >= i) throw new RangeError("Attempt to allocate Buffer larger than maximum size: 0x" + i.toString(16) + " bytes");
      return g | 0;
    }
    function m(g) {
      return +g != g && (g = 0), s.alloc(+g);
    }
    s.isBuffer = function(u) {
      return u != null && u._isBuffer === true && u !== s.prototype;
    }, s.compare = function(u, d) {
      if (He(u, Uint8Array) && (u = s.from(u, u.offset, u.byteLength)), He(d, Uint8Array) && (d = s.from(d, d.offset, d.byteLength)), !s.isBuffer(u) || !s.isBuffer(d)) throw new TypeError('The "buf1", "buf2" arguments must be one of type Buffer or Uint8Array');
      if (u === d) return 0;
      let w = u.length, T = d.length;
      for (let P = 0, z = Math.min(w, T); P < z; ++P) if (u[P] !== d[P]) {
        w = u[P], T = d[P];
        break;
      }
      return w < T ? -1 : T < w ? 1 : 0;
    }, s.isEncoding = function(u) {
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
    }, s.concat = function(u, d) {
      if (!Array.isArray(u)) throw new TypeError('"list" argument must be an Array of Buffers');
      if (u.length === 0) return s.alloc(0);
      let w;
      if (d === void 0) for (d = 0, w = 0; w < u.length; ++w) d += u[w].length;
      const T = s.allocUnsafe(d);
      let P = 0;
      for (w = 0; w < u.length; ++w) {
        let z = u[w];
        if (He(z, Uint8Array)) P + z.length > T.length ? (s.isBuffer(z) || (z = s.from(z)), z.copy(T, P)) : Uint8Array.prototype.set.call(T, z, P);
        else if (s.isBuffer(z)) z.copy(T, P);
        else throw new TypeError('"list" argument must be an Array of Buffers');
        P += z.length;
      }
      return T;
    };
    function v(g, u) {
      if (s.isBuffer(g)) return g.length;
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
          return ae(g).length;
        default:
          if (T) return w ? -1 : he(g).length;
          u = ("" + u).toLowerCase(), T = true;
      }
    }
    s.byteLength = v;
    function E(g, u, d) {
      let w = false;
      if ((u === void 0 || u < 0) && (u = 0), u > this.length || ((d === void 0 || d > this.length) && (d = this.length), d <= 0) || (d >>>= 0, u >>>= 0, d <= u)) return "";
      for (g || (g = "utf8"); ; ) switch (g) {
        case "hex":
          return $(this, u, d);
        case "utf8":
        case "utf-8":
          return O(this, u, d);
        case "ascii":
          return te(this, u, d);
        case "latin1":
        case "binary":
          return _(this, u, d);
        case "base64":
          return W(this, u, d);
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
    s.prototype._isBuffer = true;
    function A(g, u, d) {
      const w = g[u];
      g[u] = g[d], g[d] = w;
    }
    s.prototype.swap16 = function() {
      const u = this.length;
      if (u % 2 !== 0) throw new RangeError("Buffer size must be a multiple of 16-bits");
      for (let d = 0; d < u; d += 2) A(this, d, d + 1);
      return this;
    }, s.prototype.swap32 = function() {
      const u = this.length;
      if (u % 4 !== 0) throw new RangeError("Buffer size must be a multiple of 32-bits");
      for (let d = 0; d < u; d += 4) A(this, d, d + 3), A(this, d + 1, d + 2);
      return this;
    }, s.prototype.swap64 = function() {
      const u = this.length;
      if (u % 8 !== 0) throw new RangeError("Buffer size must be a multiple of 64-bits");
      for (let d = 0; d < u; d += 8) A(this, d, d + 7), A(this, d + 1, d + 6), A(this, d + 2, d + 5), A(this, d + 3, d + 4);
      return this;
    }, s.prototype.toString = function() {
      const u = this.length;
      return u === 0 ? "" : arguments.length === 0 ? O(this, 0, u) : E.apply(this, arguments);
    }, s.prototype.toLocaleString = s.prototype.toString, s.prototype.equals = function(u) {
      if (!s.isBuffer(u)) throw new TypeError("Argument must be a Buffer");
      return this === u ? true : s.compare(this, u) === 0;
    }, s.prototype.inspect = function() {
      let u = "";
      const d = e.INSPECT_MAX_BYTES;
      return u = this.toString("hex", 0, d).replace(/(.{2})/g, "$1 ").trim(), this.length > d && (u += " ... "), "<Buffer " + u + ">";
    }, r && (s.prototype[r] = s.prototype.inspect), s.prototype.compare = function(u, d, w, T, P) {
      if (He(u, Uint8Array) && (u = s.from(u, u.offset, u.byteLength)), !s.isBuffer(u)) throw new TypeError('The "target" argument must be one of type Buffer or Uint8Array. Received type ' + typeof u);
      if (d === void 0 && (d = 0), w === void 0 && (w = u ? u.length : 0), T === void 0 && (T = 0), P === void 0 && (P = this.length), d < 0 || w > u.length || T < 0 || P > this.length) throw new RangeError("out of range index");
      if (T >= P && d >= w) return 0;
      if (T >= P) return -1;
      if (d >= w) return 1;
      if (d >>>= 0, w >>>= 0, T >>>= 0, P >>>= 0, this === u) return 0;
      let z = P - T, de = w - d;
      const ke = Math.min(z, de), xe = this.slice(T, P), Ce = u.slice(d, w);
      for (let Le = 0; Le < ke; ++Le) if (xe[Le] !== Ce[Le]) {
        z = xe[Le], de = Ce[Le];
        break;
      }
      return z < de ? -1 : de < z ? 1 : 0;
    };
    function F(g, u, d, w, T) {
      if (g.length === 0) return -1;
      if (typeof d == "string" ? (w = d, d = 0) : d > 2147483647 ? d = 2147483647 : d < -2147483648 && (d = -2147483648), d = +d, It(d) && (d = T ? 0 : g.length - 1), d < 0 && (d = g.length + d), d >= g.length) {
        if (T) return -1;
        d = g.length - 1;
      } else if (d < 0) if (T) d = 0;
      else return -1;
      if (typeof u == "string" && (u = s.from(u, w)), s.isBuffer(u)) return u.length === 0 ? -1 : R(g, u, d, w, T);
      if (typeof u == "number") return u = u & 255, typeof Uint8Array.prototype.indexOf == "function" ? T ? Uint8Array.prototype.indexOf.call(g, u, d) : Uint8Array.prototype.lastIndexOf.call(g, u, d) : R(g, [
        u
      ], d, w, T);
      throw new TypeError("val must be string, number or Buffer");
    }
    function R(g, u, d, w, T) {
      let P = 1, z = g.length, de = u.length;
      if (w !== void 0 && (w = String(w).toLowerCase(), w === "ucs2" || w === "ucs-2" || w === "utf16le" || w === "utf-16le")) {
        if (g.length < 2 || u.length < 2) return -1;
        P = 2, z /= 2, de /= 2, d /= 2;
      }
      function ke(Ce, Le) {
        return P === 1 ? Ce[Le] : Ce.readUInt16BE(Le * P);
      }
      let xe;
      if (T) {
        let Ce = -1;
        for (xe = d; xe < z; xe++) if (ke(g, xe) === ke(u, Ce === -1 ? 0 : xe - Ce)) {
          if (Ce === -1 && (Ce = xe), xe - Ce + 1 === de) return Ce * P;
        } else Ce !== -1 && (xe -= xe - Ce), Ce = -1;
      } else for (d + de > z && (d = z - de), xe = d; xe >= 0; xe--) {
        let Ce = true;
        for (let Le = 0; Le < de; Le++) if (ke(g, xe + Le) !== ke(u, Le)) {
          Ce = false;
          break;
        }
        if (Ce) return xe;
      }
      return -1;
    }
    s.prototype.includes = function(u, d, w) {
      return this.indexOf(u, d, w) !== -1;
    }, s.prototype.indexOf = function(u, d, w) {
      return F(this, u, d, w, true);
    }, s.prototype.lastIndexOf = function(u, d, w) {
      return F(this, u, d, w, false);
    };
    function L(g, u, d, w) {
      d = Number(d) || 0;
      const T = g.length - d;
      w ? (w = Number(w), w > T && (w = T)) : w = T;
      const P = u.length;
      w > P / 2 && (w = P / 2);
      let z;
      for (z = 0; z < w; ++z) {
        const de = parseInt(u.substr(z * 2, 2), 16);
        if (It(de)) return z;
        g[d + z] = de;
      }
      return z;
    }
    function x(g, u, d, w) {
      return U(he(u, g.length - d), g, d, w);
    }
    function G(g, u, d, w) {
      return U(vt(u), g, d, w);
    }
    function V(g, u, d, w) {
      return U(ae(u), g, d, w);
    }
    function B(g, u, d, w) {
      return U(se(u, g.length - d), g, d, w);
    }
    s.prototype.write = function(u, d, w, T) {
      if (d === void 0) T = "utf8", w = this.length, d = 0;
      else if (w === void 0 && typeof d == "string") T = d, w = this.length, d = 0;
      else if (isFinite(d)) d = d >>> 0, isFinite(w) ? (w = w >>> 0, T === void 0 && (T = "utf8")) : (T = w, w = void 0);
      else throw new Error("Buffer.write(string, encoding, offset[, length]) is no longer supported");
      const P = this.length - d;
      if ((w === void 0 || w > P) && (w = P), u.length > 0 && (w < 0 || d < 0) || d > this.length) throw new RangeError("Attempt to write outside buffer bounds");
      T || (T = "utf8");
      let z = false;
      for (; ; ) switch (T) {
        case "hex":
          return L(this, u, d, w);
        case "utf8":
        case "utf-8":
          return x(this, u, d, w);
        case "ascii":
        case "latin1":
        case "binary":
          return G(this, u, d, w);
        case "base64":
          return V(this, u, d, w);
        case "ucs2":
        case "ucs-2":
        case "utf16le":
        case "utf-16le":
          return B(this, u, d, w);
        default:
          if (z) throw new TypeError("Unknown encoding: " + T);
          T = ("" + T).toLowerCase(), z = true;
      }
    }, s.prototype.toJSON = function() {
      return {
        type: "Buffer",
        data: Array.prototype.slice.call(this._arr || this, 0)
      };
    };
    function W(g, u, d) {
      return u === 0 && d === g.length ? t.fromByteArray(g) : t.fromByteArray(g.slice(u, d));
    }
    function O(g, u, d) {
      d = Math.min(g.length, d);
      const w = [];
      let T = u;
      for (; T < d; ) {
        const P = g[T];
        let z = null, de = P > 239 ? 4 : P > 223 ? 3 : P > 191 ? 2 : 1;
        if (T + de <= d) {
          let ke, xe, Ce, Le;
          switch (de) {
            case 1:
              P < 128 && (z = P);
              break;
            case 2:
              ke = g[T + 1], (ke & 192) === 128 && (Le = (P & 31) << 6 | ke & 63, Le > 127 && (z = Le));
              break;
            case 3:
              ke = g[T + 1], xe = g[T + 2], (ke & 192) === 128 && (xe & 192) === 128 && (Le = (P & 15) << 12 | (ke & 63) << 6 | xe & 63, Le > 2047 && (Le < 55296 || Le > 57343) && (z = Le));
              break;
            case 4:
              ke = g[T + 1], xe = g[T + 2], Ce = g[T + 3], (ke & 192) === 128 && (xe & 192) === 128 && (Ce & 192) === 128 && (Le = (P & 15) << 18 | (ke & 63) << 12 | (xe & 63) << 6 | Ce & 63, Le > 65535 && Le < 1114112 && (z = Le));
          }
        }
        z === null ? (z = 65533, de = 1) : z > 65535 && (z -= 65536, w.push(z >>> 10 & 1023 | 55296), z = 56320 | z & 1023), w.push(z), T += de;
      }
      return fe(w);
    }
    const re = 4096;
    function fe(g) {
      const u = g.length;
      if (u <= re) return String.fromCharCode.apply(String, g);
      let d = "", w = 0;
      for (; w < u; ) d += String.fromCharCode.apply(String, g.slice(w, w += re));
      return d;
    }
    function te(g, u, d) {
      let w = "";
      d = Math.min(g.length, d);
      for (let T = u; T < d; ++T) w += String.fromCharCode(g[T] & 127);
      return w;
    }
    function _(g, u, d) {
      let w = "";
      d = Math.min(g.length, d);
      for (let T = u; T < d; ++T) w += String.fromCharCode(g[T]);
      return w;
    }
    function $(g, u, d) {
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
    s.prototype.slice = function(u, d) {
      const w = this.length;
      u = ~~u, d = d === void 0 ? w : ~~d, u < 0 ? (u += w, u < 0 && (u = 0)) : u > w && (u = w), d < 0 ? (d += w, d < 0 && (d = 0)) : d > w && (d = w), d < u && (d = u);
      const T = this.subarray(u, d);
      return Object.setPrototypeOf(T, s.prototype), T;
    };
    function D(g, u, d) {
      if (g % 1 !== 0 || g < 0) throw new RangeError("offset is not uint");
      if (g + u > d) throw new RangeError("Trying to access beyond buffer length");
    }
    s.prototype.readUintLE = s.prototype.readUIntLE = function(u, d, w) {
      u = u >>> 0, d = d >>> 0, w || D(u, d, this.length);
      let T = this[u], P = 1, z = 0;
      for (; ++z < d && (P *= 256); ) T += this[u + z] * P;
      return T;
    }, s.prototype.readUintBE = s.prototype.readUIntBE = function(u, d, w) {
      u = u >>> 0, d = d >>> 0, w || D(u, d, this.length);
      let T = this[u + --d], P = 1;
      for (; d > 0 && (P *= 256); ) T += this[u + --d] * P;
      return T;
    }, s.prototype.readUint8 = s.prototype.readUInt8 = function(u, d) {
      return u = u >>> 0, d || D(u, 1, this.length), this[u];
    }, s.prototype.readUint16LE = s.prototype.readUInt16LE = function(u, d) {
      return u = u >>> 0, d || D(u, 2, this.length), this[u] | this[u + 1] << 8;
    }, s.prototype.readUint16BE = s.prototype.readUInt16BE = function(u, d) {
      return u = u >>> 0, d || D(u, 2, this.length), this[u] << 8 | this[u + 1];
    }, s.prototype.readUint32LE = s.prototype.readUInt32LE = function(u, d) {
      return u = u >>> 0, d || D(u, 4, this.length), (this[u] | this[u + 1] << 8 | this[u + 2] << 16) + this[u + 3] * 16777216;
    }, s.prototype.readUint32BE = s.prototype.readUInt32BE = function(u, d) {
      return u = u >>> 0, d || D(u, 4, this.length), this[u] * 16777216 + (this[u + 1] << 16 | this[u + 2] << 8 | this[u + 3]);
    }, s.prototype.readBigUInt64LE = st(function(u) {
      u = u >>> 0, mt(u, "offset");
      const d = this[u], w = this[u + 7];
      (d === void 0 || w === void 0) && Xe(u, this.length - 8);
      const T = d + this[++u] * 2 ** 8 + this[++u] * 2 ** 16 + this[++u] * 2 ** 24, P = this[++u] + this[++u] * 2 ** 8 + this[++u] * 2 ** 16 + w * 2 ** 24;
      return BigInt(T) + (BigInt(P) << BigInt(32));
    }), s.prototype.readBigUInt64BE = st(function(u) {
      u = u >>> 0, mt(u, "offset");
      const d = this[u], w = this[u + 7];
      (d === void 0 || w === void 0) && Xe(u, this.length - 8);
      const T = d * 2 ** 24 + this[++u] * 2 ** 16 + this[++u] * 2 ** 8 + this[++u], P = this[++u] * 2 ** 24 + this[++u] * 2 ** 16 + this[++u] * 2 ** 8 + w;
      return (BigInt(T) << BigInt(32)) + BigInt(P);
    }), s.prototype.readIntLE = function(u, d, w) {
      u = u >>> 0, d = d >>> 0, w || D(u, d, this.length);
      let T = this[u], P = 1, z = 0;
      for (; ++z < d && (P *= 256); ) T += this[u + z] * P;
      return P *= 128, T >= P && (T -= Math.pow(2, 8 * d)), T;
    }, s.prototype.readIntBE = function(u, d, w) {
      u = u >>> 0, d = d >>> 0, w || D(u, d, this.length);
      let T = d, P = 1, z = this[u + --T];
      for (; T > 0 && (P *= 256); ) z += this[u + --T] * P;
      return P *= 128, z >= P && (z -= Math.pow(2, 8 * d)), z;
    }, s.prototype.readInt8 = function(u, d) {
      return u = u >>> 0, d || D(u, 1, this.length), this[u] & 128 ? (255 - this[u] + 1) * -1 : this[u];
    }, s.prototype.readInt16LE = function(u, d) {
      u = u >>> 0, d || D(u, 2, this.length);
      const w = this[u] | this[u + 1] << 8;
      return w & 32768 ? w | 4294901760 : w;
    }, s.prototype.readInt16BE = function(u, d) {
      u = u >>> 0, d || D(u, 2, this.length);
      const w = this[u + 1] | this[u] << 8;
      return w & 32768 ? w | 4294901760 : w;
    }, s.prototype.readInt32LE = function(u, d) {
      return u = u >>> 0, d || D(u, 4, this.length), this[u] | this[u + 1] << 8 | this[u + 2] << 16 | this[u + 3] << 24;
    }, s.prototype.readInt32BE = function(u, d) {
      return u = u >>> 0, d || D(u, 4, this.length), this[u] << 24 | this[u + 1] << 16 | this[u + 2] << 8 | this[u + 3];
    }, s.prototype.readBigInt64LE = st(function(u) {
      u = u >>> 0, mt(u, "offset");
      const d = this[u], w = this[u + 7];
      (d === void 0 || w === void 0) && Xe(u, this.length - 8);
      const T = this[u + 4] + this[u + 5] * 2 ** 8 + this[u + 6] * 2 ** 16 + (w << 24);
      return (BigInt(T) << BigInt(32)) + BigInt(d + this[++u] * 2 ** 8 + this[++u] * 2 ** 16 + this[++u] * 2 ** 24);
    }), s.prototype.readBigInt64BE = st(function(u) {
      u = u >>> 0, mt(u, "offset");
      const d = this[u], w = this[u + 7];
      (d === void 0 || w === void 0) && Xe(u, this.length - 8);
      const T = (d << 24) + this[++u] * 2 ** 16 + this[++u] * 2 ** 8 + this[++u];
      return (BigInt(T) << BigInt(32)) + BigInt(this[++u] * 2 ** 24 + this[++u] * 2 ** 16 + this[++u] * 2 ** 8 + w);
    }), s.prototype.readFloatLE = function(u, d) {
      return u = u >>> 0, d || D(u, 4, this.length), n.read(this, u, true, 23, 4);
    }, s.prototype.readFloatBE = function(u, d) {
      return u = u >>> 0, d || D(u, 4, this.length), n.read(this, u, false, 23, 4);
    }, s.prototype.readDoubleLE = function(u, d) {
      return u = u >>> 0, d || D(u, 8, this.length), n.read(this, u, true, 52, 8);
    }, s.prototype.readDoubleBE = function(u, d) {
      return u = u >>> 0, d || D(u, 8, this.length), n.read(this, u, false, 52, 8);
    };
    function C(g, u, d, w, T, P) {
      if (!s.isBuffer(g)) throw new TypeError('"buffer" argument must be a Buffer instance');
      if (u > T || u < P) throw new RangeError('"value" argument is out of bounds');
      if (d + w > g.length) throw new RangeError("Index out of range");
    }
    s.prototype.writeUintLE = s.prototype.writeUIntLE = function(u, d, w, T) {
      if (u = +u, d = d >>> 0, w = w >>> 0, !T) {
        const de = Math.pow(2, 8 * w) - 1;
        C(this, u, d, w, de, 0);
      }
      let P = 1, z = 0;
      for (this[d] = u & 255; ++z < w && (P *= 256); ) this[d + z] = u / P & 255;
      return d + w;
    }, s.prototype.writeUintBE = s.prototype.writeUIntBE = function(u, d, w, T) {
      if (u = +u, d = d >>> 0, w = w >>> 0, !T) {
        const de = Math.pow(2, 8 * w) - 1;
        C(this, u, d, w, de, 0);
      }
      let P = w - 1, z = 1;
      for (this[d + P] = u & 255; --P >= 0 && (z *= 256); ) this[d + P] = u / z & 255;
      return d + w;
    }, s.prototype.writeUint8 = s.prototype.writeUInt8 = function(u, d, w) {
      return u = +u, d = d >>> 0, w || C(this, u, d, 1, 255, 0), this[d] = u & 255, d + 1;
    }, s.prototype.writeUint16LE = s.prototype.writeUInt16LE = function(u, d, w) {
      return u = +u, d = d >>> 0, w || C(this, u, d, 2, 65535, 0), this[d] = u & 255, this[d + 1] = u >>> 8, d + 2;
    }, s.prototype.writeUint16BE = s.prototype.writeUInt16BE = function(u, d, w) {
      return u = +u, d = d >>> 0, w || C(this, u, d, 2, 65535, 0), this[d] = u >>> 8, this[d + 1] = u & 255, d + 2;
    }, s.prototype.writeUint32LE = s.prototype.writeUInt32LE = function(u, d, w) {
      return u = +u, d = d >>> 0, w || C(this, u, d, 4, 4294967295, 0), this[d + 3] = u >>> 24, this[d + 2] = u >>> 16, this[d + 1] = u >>> 8, this[d] = u & 255, d + 4;
    }, s.prototype.writeUint32BE = s.prototype.writeUInt32BE = function(u, d, w) {
      return u = +u, d = d >>> 0, w || C(this, u, d, 4, 4294967295, 0), this[d] = u >>> 24, this[d + 1] = u >>> 16, this[d + 2] = u >>> 8, this[d + 3] = u & 255, d + 4;
    };
    function Y(g, u, d, w, T) {
      at(u, w, T, g, d, 7);
      let P = Number(u & BigInt(4294967295));
      g[d++] = P, P = P >> 8, g[d++] = P, P = P >> 8, g[d++] = P, P = P >> 8, g[d++] = P;
      let z = Number(u >> BigInt(32) & BigInt(4294967295));
      return g[d++] = z, z = z >> 8, g[d++] = z, z = z >> 8, g[d++] = z, z = z >> 8, g[d++] = z, d;
    }
    function ie(g, u, d, w, T) {
      at(u, w, T, g, d, 7);
      let P = Number(u & BigInt(4294967295));
      g[d + 7] = P, P = P >> 8, g[d + 6] = P, P = P >> 8, g[d + 5] = P, P = P >> 8, g[d + 4] = P;
      let z = Number(u >> BigInt(32) & BigInt(4294967295));
      return g[d + 3] = z, z = z >> 8, g[d + 2] = z, z = z >> 8, g[d + 1] = z, z = z >> 8, g[d] = z, d + 8;
    }
    s.prototype.writeBigUInt64LE = st(function(u, d = 0) {
      return Y(this, u, d, BigInt(0), BigInt("0xffffffffffffffff"));
    }), s.prototype.writeBigUInt64BE = st(function(u, d = 0) {
      return ie(this, u, d, BigInt(0), BigInt("0xffffffffffffffff"));
    }), s.prototype.writeIntLE = function(u, d, w, T) {
      if (u = +u, d = d >>> 0, !T) {
        const ke = Math.pow(2, 8 * w - 1);
        C(this, u, d, w, ke - 1, -ke);
      }
      let P = 0, z = 1, de = 0;
      for (this[d] = u & 255; ++P < w && (z *= 256); ) u < 0 && de === 0 && this[d + P - 1] !== 0 && (de = 1), this[d + P] = (u / z >> 0) - de & 255;
      return d + w;
    }, s.prototype.writeIntBE = function(u, d, w, T) {
      if (u = +u, d = d >>> 0, !T) {
        const ke = Math.pow(2, 8 * w - 1);
        C(this, u, d, w, ke - 1, -ke);
      }
      let P = w - 1, z = 1, de = 0;
      for (this[d + P] = u & 255; --P >= 0 && (z *= 256); ) u < 0 && de === 0 && this[d + P + 1] !== 0 && (de = 1), this[d + P] = (u / z >> 0) - de & 255;
      return d + w;
    }, s.prototype.writeInt8 = function(u, d, w) {
      return u = +u, d = d >>> 0, w || C(this, u, d, 1, 127, -128), u < 0 && (u = 255 + u + 1), this[d] = u & 255, d + 1;
    }, s.prototype.writeInt16LE = function(u, d, w) {
      return u = +u, d = d >>> 0, w || C(this, u, d, 2, 32767, -32768), this[d] = u & 255, this[d + 1] = u >>> 8, d + 2;
    }, s.prototype.writeInt16BE = function(u, d, w) {
      return u = +u, d = d >>> 0, w || C(this, u, d, 2, 32767, -32768), this[d] = u >>> 8, this[d + 1] = u & 255, d + 2;
    }, s.prototype.writeInt32LE = function(u, d, w) {
      return u = +u, d = d >>> 0, w || C(this, u, d, 4, 2147483647, -2147483648), this[d] = u & 255, this[d + 1] = u >>> 8, this[d + 2] = u >>> 16, this[d + 3] = u >>> 24, d + 4;
    }, s.prototype.writeInt32BE = function(u, d, w) {
      return u = +u, d = d >>> 0, w || C(this, u, d, 4, 2147483647, -2147483648), u < 0 && (u = 4294967295 + u + 1), this[d] = u >>> 24, this[d + 1] = u >>> 16, this[d + 2] = u >>> 8, this[d + 3] = u & 255, d + 4;
    }, s.prototype.writeBigInt64LE = st(function(u, d = 0) {
      return Y(this, u, d, -BigInt("0x8000000000000000"), BigInt("0x7fffffffffffffff"));
    }), s.prototype.writeBigInt64BE = st(function(u, d = 0) {
      return ie(this, u, d, -BigInt("0x8000000000000000"), BigInt("0x7fffffffffffffff"));
    });
    function _e(g, u, d, w, T, P) {
      if (d + w > g.length) throw new RangeError("Index out of range");
      if (d < 0) throw new RangeError("Index out of range");
    }
    function Se(g, u, d, w, T) {
      return u = +u, d = d >>> 0, T || _e(g, u, d, 4), n.write(g, u, d, w, 23, 4), d + 4;
    }
    s.prototype.writeFloatLE = function(u, d, w) {
      return Se(this, u, d, true, w);
    }, s.prototype.writeFloatBE = function(u, d, w) {
      return Se(this, u, d, false, w);
    };
    function oe(g, u, d, w, T) {
      return u = +u, d = d >>> 0, T || _e(g, u, d, 8), n.write(g, u, d, w, 52, 8), d + 8;
    }
    s.prototype.writeDoubleLE = function(u, d, w) {
      return oe(this, u, d, true, w);
    }, s.prototype.writeDoubleBE = function(u, d, w) {
      return oe(this, u, d, false, w);
    }, s.prototype.copy = function(u, d, w, T) {
      if (!s.isBuffer(u)) throw new TypeError("argument should be a Buffer");
      if (w || (w = 0), !T && T !== 0 && (T = this.length), d >= u.length && (d = u.length), d || (d = 0), T > 0 && T < w && (T = w), T === w || u.length === 0 || this.length === 0) return 0;
      if (d < 0) throw new RangeError("targetStart out of bounds");
      if (w < 0 || w >= this.length) throw new RangeError("Index out of range");
      if (T < 0) throw new RangeError("sourceEnd out of bounds");
      T > this.length && (T = this.length), u.length - d < T - w && (T = u.length - d + w);
      const P = T - w;
      return this === u && typeof Uint8Array.prototype.copyWithin == "function" ? this.copyWithin(d, w, T) : Uint8Array.prototype.set.call(u, this.subarray(w, T), d), P;
    }, s.prototype.fill = function(u, d, w, T) {
      if (typeof u == "string") {
        if (typeof d == "string" ? (T = d, d = 0, w = this.length) : typeof w == "string" && (T = w, w = this.length), T !== void 0 && typeof T != "string") throw new TypeError("encoding must be a string");
        if (typeof T == "string" && !s.isEncoding(T)) throw new TypeError("Unknown encoding: " + T);
        if (u.length === 1) {
          const z = u.charCodeAt(0);
          (T === "utf8" && z < 128 || T === "latin1") && (u = z);
        }
      } else typeof u == "number" ? u = u & 255 : typeof u == "boolean" && (u = Number(u));
      if (d < 0 || this.length < d || this.length < w) throw new RangeError("Out of range index");
      if (w <= d) return this;
      d = d >>> 0, w = w === void 0 ? this.length : w >>> 0, u || (u = 0);
      let P;
      if (typeof u == "number") for (P = d; P < w; ++P) this[P] = u;
      else {
        const z = s.isBuffer(u) ? u : s.from(u, T), de = z.length;
        if (de === 0) throw new TypeError('The value "' + u + '" is invalid for argument "value"');
        for (P = 0; P < w - d; ++P) this[P + d] = z[P % de];
      }
      return this;
    };
    const X = {};
    function Qe(g, u, d) {
      X[g] = class extends d {
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
    function at(g, u, d, w, T, P) {
      if (g > d || g < u) {
        const z = typeof u == "bigint" ? "n" : "";
        let de;
        throw u === 0 || u === BigInt(0) ? de = `>= 0${z} and < 2${z} ** ${(P + 1) * 8}${z}` : de = `>= -(2${z} ** ${(P + 1) * 8 - 1}${z}) and < 2 ** ${(P + 1) * 8 - 1}${z}`, new X.ERR_OUT_OF_RANGE("value", de, g);
      }
      _n(w, T, P);
    }
    function mt(g, u) {
      if (typeof g != "number") throw new X.ERR_INVALID_ARG_TYPE(u, "number", g);
    }
    function Xe(g, u, d) {
      throw Math.floor(g) !== g ? (mt(g, d), new X.ERR_OUT_OF_RANGE("offset", "an integer", g)) : u < 0 ? new X.ERR_BUFFER_OUT_OF_BOUNDS() : new X.ERR_OUT_OF_RANGE("offset", `>= 0 and <= ${u}`, g);
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
      for (let z = 0; z < w; ++z) {
        if (d = g.charCodeAt(z), d > 55295 && d < 57344) {
          if (!T) {
            if (d > 56319) {
              (u -= 3) > -1 && P.push(239, 191, 189);
              continue;
            } else if (z + 1 === w) {
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
    function se(g, u) {
      let d, w, T;
      const P = [];
      for (let z = 0; z < g.length && !((u -= 2) < 0); ++z) d = g.charCodeAt(z), w = d >> 8, T = d % 256, P.push(T), P.push(w);
      return P;
    }
    function ae(g) {
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
    function It(g) {
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
    function st(g) {
      return typeof BigInt > "u" ? yt : g;
    }
    function yt() {
      throw new Error("BigInt not supported");
    }
  })(Np);
  const qy = "modulepreload", Jy = function(e) {
    return "/" + e;
  }, Dd = {}, e0 = function(t, n, r) {
    let i = Promise.resolve();
    if (n && n.length > 0) {
      document.getElementsByTagName("link");
      const a = document.querySelector("meta[property=csp-nonce]"), s = (a == null ? void 0 : a.nonce) || (a == null ? void 0 : a.getAttribute("nonce"));
      i = Promise.allSettled(n.map((l) => {
        if (l = Jy(l), l in Dd) return;
        Dd[l] = true;
        const c = l.endsWith(".css"), h = c ? '[rel="stylesheet"]' : "";
        if (document.querySelector(`link[href="${l}"]${h}`)) return;
        const f = document.createElement("link");
        if (f.rel = c ? "stylesheet" : qy, c || (f.as = "script"), f.crossOrigin = "", f.href = l, s && f.setAttribute("nonce", s), document.head.appendChild(f), c) return new Promise((p, y) => {
          f.addEventListener("load", p), f.addEventListener("error", () => y(new Error(`Unable to preload CSS for ${l}`)));
        });
      }));
    }
    function o(a) {
      const s = new Event("vite:preloadError", {
        cancelable: true
      });
      if (s.payload = a, window.dispatchEvent(s), !s.defaultPrevented) throw a;
    }
    return i.then((a) => {
      for (const s of a || []) s.status === "rejected" && o(s.reason);
      return t().catch(o);
    });
  };
  const Op = Symbol("Comlink.proxy"), t0 = Symbol("Comlink.endpoint"), n0 = Symbol("Comlink.releaseProxy"), qs = Symbol("Comlink.finalizer"), Ea = Symbol("Comlink.thrown"), Gp = (e) => typeof e == "object" && e !== null || typeof e == "function", r0 = {
    canHandle: (e) => Gp(e) && e[Op],
    serialize(e) {
      const { port1: t, port2: n } = new MessageChannel();
      return Bp(e, t), [
        n,
        [
          n
        ]
      ];
    },
    deserialize(e) {
      return e.start(), $p(e);
    }
  }, i0 = {
    canHandle: (e) => Gp(e) && Ea in e,
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
  }, Up = /* @__PURE__ */ new Map([
    [
      "proxy",
      r0
    ],
    [
      "throw",
      i0
    ]
  ]);
  function o0(e, t) {
    for (const n of e) if (t === n || n === "*" || n instanceof RegExp && n.test(t)) return true;
    return false;
  }
  function Bp(e, t = globalThis, n = [
    "*"
  ]) {
    t.addEventListener("message", function r(i) {
      if (!i || !i.data) return;
      if (!o0(n, i.origin)) {
        console.warn(`Invalid origin '${i.origin}' for comlink proxy`);
        return;
      }
      const { id: o, type: a, path: s } = Object.assign({
        path: []
      }, i.data), l = (i.data.argumentList || []).map(Cr);
      let c;
      try {
        const h = s.slice(0, -1).reduce((p, y) => p[y], e), f = s.reduce((p, y) => p[y], e);
        switch (a) {
          case "GET":
            c = f;
            break;
          case "SET":
            h[s.slice(-1)[0]] = Cr(i.data.value), c = true;
            break;
          case "APPLY":
            c = f.apply(h, l);
            break;
          case "CONSTRUCT":
            {
              const p = new f(...l);
              c = Xi(p);
            }
            break;
          case "ENDPOINT":
            {
              const { port1: p, port2: y } = new MessageChannel();
              Bp(e, y), c = c0(p, [
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
          [Ea]: 0
        };
      }
      Promise.resolve(c).catch((h) => ({
        value: h,
        [Ea]: 0
      })).then((h) => {
        const [f, p] = Qa(h);
        t.postMessage(Object.assign(Object.assign({}, f), {
          id: o
        }), p), a === "RELEASE" && (t.removeEventListener("message", r), Mp(t), qs in e && typeof e[qs] == "function" && e[qs]());
      }).catch((h) => {
        const [f, p] = Qa({
          value: new TypeError("Unserializable return value"),
          [Ea]: 0
        });
        t.postMessage(Object.assign(Object.assign({}, f), {
          id: o
        }), p);
      });
    }), t.start && t.start();
  }
  function a0(e) {
    return e.constructor.name === "MessagePort";
  }
  function Mp(e) {
    a0(e) && e.close();
  }
  function $p(e, t) {
    const n = /* @__PURE__ */ new Map();
    return e.addEventListener("message", function(i) {
      const { data: o } = i;
      if (!o || !o.id) return;
      const a = n.get(o.id);
      if (a) try {
        a(o);
      } finally {
        n.delete(o.id);
      }
    }), au(e, n, [], t);
  }
  function Jo(e) {
    if (e) throw new Error("Proxy has been released and is not useable");
  }
  function jp(e) {
    return Mr(e, /* @__PURE__ */ new Map(), {
      type: "RELEASE"
    }).then(() => {
      Mp(e);
    });
  }
  const Ka = /* @__PURE__ */ new WeakMap(), Ya = "FinalizationRegistry" in globalThis && new FinalizationRegistry((e) => {
    const t = (Ka.get(e) || 0) - 1;
    Ka.set(e, t), t === 0 && jp(e);
  });
  function s0(e, t) {
    const n = (Ka.get(t) || 0) + 1;
    Ka.set(t, n), Ya && Ya.register(e, t, e);
  }
  function l0(e) {
    Ya && Ya.unregister(e);
  }
  function au(e, t, n = [], r = function() {
  }) {
    let i = false;
    const o = new Proxy(r, {
      get(a, s) {
        if (Jo(i), s === n0) return () => {
          l0(o), jp(e), t.clear(), i = true;
        };
        if (s === "then") {
          if (n.length === 0) return {
            then: () => o
          };
          const l = Mr(e, t, {
            type: "GET",
            path: n.map((c) => c.toString())
          }).then(Cr);
          return l.then.bind(l);
        }
        return au(e, t, [
          ...n,
          s
        ]);
      },
      set(a, s, l) {
        Jo(i);
        const [c, h] = Qa(l);
        return Mr(e, t, {
          type: "SET",
          path: [
            ...n,
            s
          ].map((f) => f.toString()),
          value: c
        }, h).then(Cr);
      },
      apply(a, s, l) {
        Jo(i);
        const c = n[n.length - 1];
        if (c === t0) return Mr(e, t, {
          type: "ENDPOINT"
        }).then(Cr);
        if (c === "bind") return au(e, t, n.slice(0, -1));
        const [h, f] = Pd(l);
        return Mr(e, t, {
          type: "APPLY",
          path: n.map((p) => p.toString()),
          argumentList: h
        }, f).then(Cr);
      },
      construct(a, s) {
        Jo(i);
        const [l, c] = Pd(s);
        return Mr(e, t, {
          type: "CONSTRUCT",
          path: n.map((h) => h.toString()),
          argumentList: l
        }, c).then(Cr);
      }
    });
    return s0(o, e), o;
  }
  function u0(e) {
    return Array.prototype.concat.apply([], e);
  }
  function Pd(e) {
    const t = e.map(Qa);
    return [
      t.map((n) => n[0]),
      u0(t.map((n) => n[1]))
    ];
  }
  const Hp = /* @__PURE__ */ new WeakMap();
  function c0(e, t) {
    return Hp.set(e, t), e;
  }
  function Xi(e) {
    return Object.assign(e, {
      [Op]: true
    });
  }
  function Qa(e) {
    for (const [t, n] of Up) if (n.canHandle(e)) {
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
      Hp.get(e) || []
    ];
  }
  function Cr(e) {
    switch (e.type) {
      case "HANDLER":
        return Up.get(e.name).deserialize(e.value);
      case "RAW":
        return e.value;
    }
  }
  function Mr(e, t, n, r) {
    return new Promise((i) => {
      const o = d0();
      t.set(o, i), e.start && e.start(), e.postMessage(Object.assign({
        id: o
      }, n), r);
    });
  }
  function d0() {
    return new Array(4).fill(0).map(() => Math.floor(Math.random() * Number.MAX_SAFE_INTEGER).toString(16)).join("-");
  }
  const Id = (e, t) => {
    const n = t();
    return e.nodes.forEach((r) => n.addNode(r)), e.relationships.forEach((r) => n.addRelationship(r)), {
      graph: n,
      fileContents: new Map(Object.entries(e.fileContents))
    };
  }, Js = () => {
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
  }, Fd = {
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
  }, Nd = {
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
  }, zd = [
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
  ], Od = (e) => zd[e % zd.length], f0 = [
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
  ], h0 = [
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
  }, Wp = "gitnexus-llm-settings", su = () => {
    try {
      const e = localStorage.getItem(Wp);
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
  }, p0 = (e) => {
    try {
      localStorage.setItem(Wp, JSON.stringify(e));
    } catch (t) {
      console.error("Failed to save LLM settings:", t);
    }
  }, lu = () => {
    var _a2, _b, _c2, _d2, _e, _f2;
    const e = su();
    switch (e.activeProvider) {
      case "openai":
        return ((_a2 = e.openai) == null ? void 0 : _a2.apiKey) ? {
          provider: "openai",
          ...e.openai
        } : null;
      case "azure-openai":
        return !((_b = e.azureOpenAI) == null ? void 0 : _b.apiKey) || !((_c2 = e.azureOpenAI) == null ? void 0 : _c2.endpoint) ? null : {
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
  function g0(e) {
    let t = e.trim();
    return t = t.replace(/\/+$/, ""), !t.startsWith("http://") && !t.startsWith("https://") && (t.startsWith("localhost") || t.startsWith("127.0.0.1") ? t = `http://${t}` : t = `https://${t}`), t.endsWith("/api") || (t = `${t}/api`), t;
  }
  async function m0(e, t) {
    const n = t ? `${e}/repo?repo=${encodeURIComponent(t)}` : `${e}/repo`, r = await fetch(n);
    if (!r.ok) throw new Error(`Server returned ${r.status}: ${r.statusText}`);
    const i = await r.json();
    return {
      ...i,
      repoPath: i.repoPath ?? i.path
    };
  }
  async function v0(e, t, n, r) {
    const i = r ? `${e}/graph?repo=${encodeURIComponent(r)}` : `${e}/graph`, o = await fetch(i, {
      signal: n
    });
    if (!o.ok) throw new Error(`Server returned ${o.status}: ${o.statusText}`);
    const a = o.headers.get("Content-Length"), s = a ? parseInt(a, 10) : null;
    if (!o.body) return await o.json();
    const l = o.body.getReader(), c = [];
    let h = 0;
    for (; ; ) {
      const { done: k, value: b } = await l.read();
      if (k) break;
      c.push(b), h += b.length, t == null ? void 0 : t(h, s);
    }
    const f = new Uint8Array(h);
    let p = 0;
    for (const k of c) f.set(k, p), p += k.length;
    const y = new TextDecoder().decode(f);
    return JSON.parse(y);
  }
  function y0(e) {
    const t = {};
    for (const n of e) n.label === "File" && n.properties.content && (t[n.properties.filePath] = n.properties.content);
    return t;
  }
  async function w0(e, t, n, r) {
    const i = g0(e);
    t == null ? void 0 : t("validating", 0, null);
    const o = await m0(i, r);
    t == null ? void 0 : t("downloading", 0, null);
    const { nodes: a, relationships: s } = await v0(i, (c, h) => t == null ? void 0 : t("downloading", c, h), n, r);
    t == null ? void 0 : t("extracting", 0, null);
    const l = y0(a);
    return {
      nodes: a,
      relationships: s,
      fileContents: l,
      repoInfo: o
    };
  }
  const Vp = N.createContext(null), E0 = ({ children: e }) => {
    const [t, n] = N.useState("onboarding"), [r, i] = N.useState(null), [o, a] = N.useState(/* @__PURE__ */ new Map()), [s, l] = N.useState(null), [c, h] = N.useState(false), [f, p] = N.useState("code"), y = N.useCallback(() => {
      Ce(true);
    }, []), k = N.useCallback(() => {
      h(true), p("chat");
    }, []), [b, I] = N.useState(f0), [S, m] = N.useState(h0), [v, E] = N.useState(null), [A, F] = N.useState(/* @__PURE__ */ new Set()), [R, L] = N.useState(null), [x, G] = N.useState(/* @__PURE__ */ new Set()), [V, B] = N.useState(/* @__PURE__ */ new Set()), [W, O] = N.useState(/* @__PURE__ */ new Set()), [re, fe] = N.useState(true), te = N.useCallback(() => {
      fe((Z) => !Z);
    }, []), _ = N.useCallback(() => {
      B(/* @__PURE__ */ new Set());
    }, []), $ = N.useCallback(() => {
      O(/* @__PURE__ */ new Set());
    }, []), H = N.useCallback(() => {
      F(/* @__PURE__ */ new Set()), L(null);
    }, []), [D, C] = N.useState(/* @__PURE__ */ new Map()), Y = N.useRef(null), ie = N.useCallback((Z, ne) => {
      const ce = Date.now(), pe = ne === "pulse" ? 2e3 : ne === "ripple" ? 3e3 : 4e3;
      C((ge) => {
        const le = new Map(ge);
        for (const ye of Z) le.set(ye, {
          type: ne,
          startTime: ce,
          duration: pe
        });
        return le;
      }), setTimeout(() => {
        C((ge) => {
          const le = new Map(ge);
          for (const ye of Z) {
            const $t = le.get(ye);
            $t && $t.startTime === ce && le.delete(ye);
          }
          return le;
        });
      }, pe + 100);
    }, []), _e = N.useCallback(() => {
      C(/* @__PURE__ */ new Map()), Y.current && (clearInterval(Y.current), Y.current = null);
    }, []), [Se, oe] = N.useState(null), [X, Qe] = N.useState(""), [ze, _n] = N.useState(null), [at, mt] = N.useState([]), [Xe, me] = N.useState("idle"), [ve, he] = N.useState(null), [vt, se] = N.useState(su), [ae, U] = N.useState(false), [He, It] = N.useState(false), [ln, st] = N.useState(false), [yt, g] = N.useState(null), [u, d] = N.useState([]), [w, T] = N.useState(false), [P, z] = N.useState([]), [de, ke] = N.useState([]), [xe, Ce] = N.useState(false), [Le, Io] = N.useState(null), Xn = N.useCallback((Z) => Z.replace(/\\/g, "/").replace(/^\.?\//, ""), []), ks = N.useCallback((Z) => {
      const ne = Xn(Z).toLowerCase();
      if (!ne) return null;
      for (const ge of o.keys()) if (Xn(ge).toLowerCase() === ne) return ge;
      let ce = null;
      for (const ge of o.keys()) {
        const le = Xn(ge).toLowerCase();
        if (le.endsWith(ne)) {
          const ye = 1e3 - le.length;
          (!ce || ye > ce.score) && (ce = {
            path: ge,
            score: ye
          });
        }
      }
      if (ce) return ce.path;
      const pe = ne.split("/").filter(Boolean);
      for (const ge of o.keys()) {
        const le = Xn(ge).toLowerCase().split("/").filter(Boolean);
        let ye = 0;
        for (const $t of pe) {
          const un = le.findIndex((lt, We) => We >= ye && lt.includes($t));
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
      Xn
    ]), Ec = N.useCallback((Z) => {
      var _a2;
      if (!r) return;
      const ne = Xn(Z);
      return (_a2 = r.nodes.find((pe) => pe.label === "File" && Xn(pe.properties.filePath) === ne)) == null ? void 0 : _a2.id;
    }, [
      r,
      Xn
    ]), Fo = N.useCallback((Z) => {
      const ne = `ref-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, ce = {
        ...Z,
        id: ne
      };
      ke((pe) => pe.some((le) => le.filePath === Z.filePath && le.startLine === Z.startLine && le.endLine === Z.endLine) ? pe : [
        ...pe,
        ce
      ]), Ce(true), Io({
        filePath: Z.filePath,
        startLine: Z.startLine,
        endLine: Z.endLine,
        ts: Date.now()
      }), Z.nodeId && Z.source === "ai" && G((pe) => /* @__PURE__ */ new Set([
        ...pe,
        Z.nodeId
      ]));
    }, []), bs = N.useCallback(() => {
      ke((Z) => {
        const ne = Z.filter((ge) => ge.source === "ai"), ce = Z.filter((ge) => ge.source !== "ai"), pe = new Set(ne.map((ge) => ge.nodeId).filter(Boolean));
        return pe.size > 0 && G((ge) => {
          const le = new Set(ge);
          for (const ye of pe) le.delete(ye);
          return le;
        }), ce.length === 0 && !s && Ce(false), ce;
      });
    }, [
      R,
      s
    ]);
    N.useEffect(() => {
      s && Ce(true);
    }, [
      s
    ]);
    const Sc = N.useRef(null), Ft = N.useRef(null);
    N.useEffect(() => {
      const Z = new Worker(new URL("/assets/ingestion.worker-BiTDjgSE.js", import.meta.url), {
        type: "module"
      }), ne = $p(Z);
      return Sc.current = Z, Ft.current = ne, () => {
        Z.terminate(), Sc.current = null, Ft.current = null;
      };
    }, []);
    const Zg = N.useCallback(async (Z, ne, ce) => {
      const pe = Ft.current;
      if (!pe) throw new Error("Worker not initialized");
      const ge = Xi(ne), le = await pe.runPipeline(Z, ge, ce);
      return Id(le, Js);
    }, []), qg = N.useCallback(async (Z, ne, ce) => {
      const pe = Ft.current;
      if (!pe) throw new Error("Worker not initialized");
      const ge = Xi(ne), le = await pe.runPipelineFromFiles(Z, ge, ce);
      return Id(le, Js);
    }, []), Jg = N.useCallback(async (Z) => {
      const ne = Ft.current;
      if (!ne) throw new Error("Worker not initialized");
      return ne.runQuery(Z);
    }, []), em = N.useCallback(async () => {
      const Z = Ft.current;
      if (!Z) return false;
      try {
        return await Z.isReady();
      } catch {
        return false;
      }
    }, []), No = N.useCallback(async (Z) => {
      var _a2;
      const ne = Ft.current;
      if (!ne) throw new Error("Worker not initialized");
      me("loading"), he(null);
      try {
        const ce = Xi((pe) => {
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
        await ne.startEmbeddingPipeline(ce, Z);
      } catch (ce) {
        throw (ce == null ? void 0 : ce.name) === "WebGPUNotAvailableError" || ((_a2 = ce == null ? void 0 : ce.message) == null ? void 0 : _a2.includes("WebGPU not available")) ? me("idle") : me("error"), ce;
      }
    }, []), tm = N.useCallback(async (Z, ne = 10) => {
      const ce = Ft.current;
      if (!ce) throw new Error("Worker not initialized");
      return ce.semanticSearch(Z, ne);
    }, []), nm = N.useCallback(async (Z, ne = 5, ce = 2) => {
      const pe = Ft.current;
      if (!pe) throw new Error("Worker not initialized");
      return pe.semanticSearchWithContext(Z, ne, ce);
    }, []), rm = N.useCallback(async () => {
      const Z = Ft.current;
      return Z ? Z.testArrayParams() : {
        success: false,
        error: "Worker not initialized"
      };
    }, []), im = N.useCallback((Z) => {
      se((ne) => {
        const ce = {
          ...ne,
          ...Z
        };
        return p0(ce), ce;
      });
    }, []), om = N.useCallback(() => {
      se(su());
    }, []), xi = N.useCallback(async (Z) => {
      const ne = Ft.current;
      if (!ne) {
        g("Worker not initialized");
        return;
      }
      const ce = lu();
      if (!ce) {
        g("Please configure an LLM provider in settings");
        return;
      }
      st(true), g(null);
      try {
        const pe = Z || X || "project", ge = await ne.initializeAgent(ce, pe);
        ge.success ? (It(true), g(null)) : (g(ge.error ?? "Failed to initialize agent"), It(false));
      } catch (pe) {
        const ge = pe instanceof Error ? pe.message : String(pe);
        g(ge), It(false);
      } finally {
        st(false);
      }
    }, [
      X
    ]), am = N.useCallback(async (Z) => {
      const ne = Ft.current;
      if (!ne) {
        g("Worker not initialized");
        return;
      }
      if (bs(), _(), !He && (await xi(), !Ft.current)) return;
      const ce = {
        id: `user-${Date.now()}`,
        role: "user",
        content: Z,
        timestamp: Date.now()
      };
      if (d((lt) => [
        ...lt,
        ce
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
        ]), g(null), T(false), z([]);
        return;
      }
      T(true), z([]);
      const pe = [
        ...u,
        ce
      ].map((lt) => ({
        role: lt.role === "tool" ? "assistant" : lt.role,
        content: lt.content
      })), ge = `assistant-${Date.now()}`, le = [], ye = [];
      let $t = 0;
      const un = () => {
        const We = le.filter((we) => we.type === "reasoning" || we.type === "content").map((we) => we.content).filter(Boolean).join(`

`);
        d((we) => {
          const wt = we.find((De) => De.id === ge), cn = {
            id: ge,
            role: "assistant",
            content: We,
            steps: [
              ...le
            ],
            toolCalls: [
              ...ye
            ],
            timestamp: (wt == null ? void 0 : wt.timestamp) ?? Date.now()
          };
          return wt ? we.map((De) => De.id === ge ? cn : De) : [
            ...we,
            cn
          ];
        });
      };
      try {
        const lt = Xi((We) => {
          switch (We.type) {
            case "reasoning":
              if (We.reasoning) {
                const we = le[le.length - 1];
                we && we.type === "reasoning" ? le[le.length - 1] = {
                  ...we,
                  content: (we.content || "") + We.reasoning
                } : le.push({
                  id: `step-${$t++}`,
                  type: "reasoning",
                  content: We.reasoning
                }), un();
              }
              break;
            case "content":
              if (We.content) {
                const we = le[le.length - 1];
                we && we.type === "content" ? le[le.length - 1] = {
                  ...we,
                  content: (we.content || "") + We.content
                } : le.push({
                  id: `step-${$t++}`,
                  type: "content",
                  content: We.content
                }), un();
                const wt = le[le.length - 1], cn = wt && wt.type === "content" && wt.content || "", De = /\[\[([a-zA-Z0-9_\-./\\]+\.[a-zA-Z0-9]+)(?::(\d+)(?:[-–](\d+))?)?\]\]/g;
                let Et;
                for (; (Et = De.exec(cn)) !== null; ) {
                  const Dn = Et[1].trim(), tt = Et[2] ? parseInt(Et[2], 10) : void 0, nt = Et[3] ? parseInt(Et[3], 10) : tt, Nt = ks(Dn);
                  if (!Nt) continue;
                  const Ti = tt !== void 0 ? Math.max(0, tt - 1) : void 0, gm = nt !== void 0 ? Math.max(0, nt - 1) : Ti, mm = Ec(Nt);
                  Fo({
                    filePath: Nt,
                    startLine: Ti,
                    endLine: gm,
                    nodeId: mm,
                    label: "File",
                    name: Nt.split("/").pop() ?? Nt,
                    source: "ai"
                  });
                }
                const Ve = /\[\[(?:graph:)?(Class|Function|Method|Interface|File|Folder|Variable|Enum|Type|CodeElement):([^\]]+)\]\]/g;
                let et;
                for (; (et = Ve.exec(cn)) !== null; ) {
                  const Dn = et[1], tt = et[2].trim();
                  if (!r) continue;
                  const nt = r.nodes.find((Ti) => Ti.label === Dn && Ti.properties.name === tt);
                  if (!nt || !nt.properties.filePath) continue;
                  const Nt = ks(nt.properties.filePath);
                  Nt && Fo({
                    filePath: Nt,
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
                ye.push(we), le.push({
                  id: `step-${$t++}`,
                  type: "tool_call",
                  toolCall: we
                }), z((wt) => [
                  ...wt,
                  we
                ]), un();
              }
              break;
            case "tool_result":
              if (We.toolCall) {
                const we = We.toolCall;
                let wt = ye.findIndex((De) => De.id === we.id);
                wt < 0 && (wt = ye.findIndex((De) => De.name === we.name && De.status === "running")), wt < 0 && (wt = ye.findIndex((De) => De.name === we.name && !De.result)), wt >= 0 && (ye[wt] = {
                  ...ye[wt],
                  result: we.result,
                  status: "completed"
                });
                const cn = le.findIndex((De) => De.type === "tool_call" && De.toolCall && (De.toolCall.id === we.id || De.toolCall.name === we.name && De.toolCall.status === "running"));
                if (cn >= 0 && le[cn].toolCall && (le[cn] = {
                  ...le[cn],
                  toolCall: {
                    ...le[cn].toolCall,
                    result: we.result,
                    status: "completed"
                  }
                }), z((De) => {
                  let Et = De.findIndex((Ve) => Ve.id === we.id);
                  return Et < 0 && (Et = De.findIndex((Ve) => Ve.name === we.name && Ve.status === "running")), Et < 0 && (Et = De.findIndex((Ve) => Ve.name === we.name && !Ve.result)), Et >= 0 ? De.map((Ve, et) => et === Et ? {
                    ...Ve,
                    result: we.result,
                    status: "completed"
                  } : Ve) : De;
                }), un(), we.result) {
                  const De = we.result.match(/\[HIGHLIGHT_NODES:([^\]]+)\]/);
                  if (De) {
                    const Ve = De[1].split(",").map((et) => et.trim()).filter(Boolean);
                    if (Ve.length > 0 && r) {
                      const et = /* @__PURE__ */ new Set(), Dn = r.nodes.map((tt) => tt.id);
                      for (const tt of Ve) if (Dn.includes(tt)) et.add(tt);
                      else {
                        const nt = Dn.find((Nt) => Nt.endsWith(tt) || Nt.endsWith(":" + tt));
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
                        const nt = Dn.find((Nt) => Nt.endsWith(tt) || Nt.endsWith(":" + tt));
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
        T(false), z([]);
      }
    }, [
      u,
      He,
      xi,
      ks,
      Ec,
      Fo,
      bs,
      _,
      r,
      Xe
    ]), sm = N.useCallback(() => {
      const Z = Ft.current;
      Z && w && (Z.stopChat(), T(false), z([]));
    }, [
      w
    ]), lm = N.useCallback(() => {
      d([]), z([]), g(null);
    }, []), um = N.useCallback(async (Z) => {
      if (ze) {
        oe({
          phase: "extracting",
          percent: 0,
          message: "Switching repository...",
          detail: `Loading ${Z}`
        }), n("loading"), F(/* @__PURE__ */ new Set()), _(), $(), l(null), L(null), ke([]), Ce(false), Io(null);
        try {
          const ne = await w0(ze, (ye, $t, un) => {
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
          }, void 0, Z), ce = ne.repoInfo.repoPath, pe = ne.repoInfo.name || ce.split("/").pop() || "server-project";
          Qe(pe);
          const ge = Js();
          for (const ye of ne.nodes) ge.addNode(ye);
          for (const ye of ne.relationships) ge.addRelationship(ye);
          i(ge);
          const le = /* @__PURE__ */ new Map();
          for (const [ye, $t] of Object.entries(ne.fileContents)) le.set(ye, $t);
          a(le), n("exploring"), lu() && xi(pe), No().catch((ye) => {
            var _a2;
            (ye == null ? void 0 : ye.name) === "WebGPUNotAvailableError" || ((_a2 = ye == null ? void 0 : ye.message) == null ? void 0 : _a2.includes("WebGPU")) ? No("wasm").catch(console.warn) : console.warn("Embeddings auto-start failed:", ye);
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
      a,
      xi,
      No,
      F,
      _,
      $,
      l,
      L,
      ke,
      Ce,
      Io
    ]), cm = N.useCallback((Z) => {
      ke((ne) => {
        const ce = ne.find((ge) => ge.id === Z), pe = ne.filter((ge) => ge.id !== Z);
        return (ce == null ? void 0 : ce.nodeId) && ce.source === "ai" && (pe.some((le) => le.nodeId === ce.nodeId && le.source === "ai") || G((le) => {
          const ye = new Set(le);
          return ye.delete(ce.nodeId), ye;
        })), pe.length === 0 && !s && Ce(false), pe;
      });
    }, [
      s
    ]), dm = N.useCallback(() => {
      ke([]), Ce(false), Io(null);
    }, []), fm = N.useCallback((Z) => {
      I((ne) => ne.includes(Z) ? ne.filter((ce) => ce !== Z) : [
        ...ne,
        Z
      ]);
    }, []), hm = N.useCallback((Z) => {
      m((ne) => ne.includes(Z) ? ne.filter((ce) => ce !== Z) : [
        ...ne,
        Z
      ]);
    }, []), pm = {
      viewMode: t,
      setViewMode: n,
      graph: r,
      setGraph: i,
      fileContents: o,
      setFileContents: a,
      selectedNode: s,
      setSelectedNode: l,
      isRightPanelOpen: c,
      setRightPanelOpen: h,
      rightPanelTab: f,
      setRightPanelTab: p,
      openCodePanel: y,
      openChatPanel: k,
      visibleLabels: b,
      toggleLabelVisibility: fm,
      visibleEdgeTypes: S,
      toggleEdgeVisibility: hm,
      depthFilter: v,
      setDepthFilter: E,
      highlightedNodeIds: A,
      setHighlightedNodeIds: F,
      aiCitationHighlightedNodeIds: x,
      aiToolHighlightedNodeIds: V,
      blastRadiusNodeIds: W,
      isAIHighlightsEnabled: re,
      toggleAIHighlights: te,
      clearAIToolHighlights: _,
      clearBlastRadius: $,
      queryResult: R,
      setQueryResult: L,
      clearQueryHighlights: H,
      animatedNodes: D,
      triggerNodeAnimation: ie,
      clearAnimations: _e,
      progress: Se,
      setProgress: oe,
      projectName: X,
      setProjectName: Qe,
      serverBaseUrl: ze,
      setServerBaseUrl: _n,
      availableRepos: at,
      setAvailableRepos: mt,
      switchRepo: um,
      runPipeline: Zg,
      runPipelineFromFiles: qg,
      runQuery: Jg,
      isDatabaseReady: em,
      embeddingStatus: Xe,
      embeddingProgress: ve,
      startEmbeddings: No,
      semanticSearch: tm,
      semanticSearchWithContext: nm,
      isEmbeddingReady: Xe === "ready",
      testArrayParams: rm,
      llmSettings: vt,
      updateLLMSettings: im,
      isSettingsPanelOpen: ae,
      setSettingsPanelOpen: U,
      isAgentReady: He,
      isAgentInitializing: ln,
      agentError: yt,
      chatMessages: u,
      isChatLoading: w,
      currentToolCalls: P,
      refreshLLMSettings: om,
      initializeAgent: xi,
      sendChatMessage: am,
      stopChatResponse: sm,
      clearChat: lm,
      codeReferences: de,
      isCodePanelOpen: xe,
      setCodePanelOpen: Ce,
      addCodeReference: Fo,
      removeCodeReference: cm,
      clearAICodeReferences: bs,
      clearCodeReferences: dm,
      codeReferenceFocus: Le
    };
    return q.jsx(Vp.Provider, {
      value: pm,
      children: e
    });
  }, Kp = () => {
    const e = N.useContext(Vp);
    if (!e) throw new Error("useAppState must be used within AppStateProvider");
    return e;
  };
  const S0 = (e) => e.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase(), _0 = (e) => e.replace(/^([A-Z])|[\s-_]+(\w)/g, (t, n, r) => r ? r.toUpperCase() : n.toLowerCase()), Gd = (e) => {
    const t = _0(e);
    return t.charAt(0).toUpperCase() + t.slice(1);
  }, Yp = (...e) => e.filter((t, n, r) => !!t && t.trim() !== "" && r.indexOf(t) === n).join(" ").trim(), k0 = (e) => {
    for (const t in e) if (t.startsWith("aria-") || t === "role" || t === "title") return true;
  };
  var b0 = {
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
  const C0 = N.forwardRef(({ color: e = "currentColor", size: t = 24, strokeWidth: n = 2, absoluteStrokeWidth: r, className: i = "", children: o, iconNode: a, ...s }, l) => N.createElement("svg", {
    ref: l,
    ...b0,
    width: t,
    height: t,
    stroke: e,
    strokeWidth: r ? Number(n) * 24 / Number(t) : n,
    className: Yp("lucide", i),
    ...!o && !k0(s) && {
      "aria-hidden": "true"
    },
    ...s
  }, [
    ...a.map(([c, h]) => N.createElement(c, h)),
    ...Array.isArray(o) ? o : [
      o
    ]
  ]));
  const ms = (e, t) => {
    const n = N.forwardRef(({ className: r, ...i }, o) => N.createElement(C0, {
      ref: o,
      iconNode: t,
      className: Yp(`lucide-${S0(Gd(e))}`, `lucide-${e}`, r),
      ...i
    }));
    return n.displayName = Gd(e), n;
  };
  const x0 = [
    [
      "path",
      {
        d: "M13.659 22H18a2 2 0 0 0 2-2V8a2.4 2.4 0 0 0-.706-1.706l-3.588-3.588A2.4 2.4 0 0 0 14 2H6a2 2 0 0 0-2 2v11.5",
        key: "4pqfef"
      }
    ],
    [
      "path",
      {
        d: "M14 2v5a1 1 0 0 0 1 1h5",
        key: "wfsgrz"
      }
    ],
    [
      "path",
      {
        d: "M8 12v-1",
        key: "1ej8lb"
      }
    ],
    [
      "path",
      {
        d: "M8 18v-2",
        key: "qcmpov"
      }
    ],
    [
      "path",
      {
        d: "M8 7V6",
        key: "1nbb54"
      }
    ],
    [
      "circle",
      {
        cx: "8",
        cy: "20",
        r: "2",
        key: "ckkr5m"
      }
    ]
  ], T0 = ms("file-archive", x0);
  const R0 = [
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
  ], A0 = ms("focus", R0);
  const L0 = [
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
  ], D0 = ms("rotate-ccw", L0);
  const P0 = [
    [
      "path",
      {
        d: "M12 3v12",
        key: "1x0j5s"
      }
    ],
    [
      "path",
      {
        d: "m17 8-5-5-5 5",
        key: "7q97r8"
      }
    ],
    [
      "path",
      {
        d: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4",
        key: "ih7n3h"
      }
    ]
  ], I0 = ms("upload", P0), F0 = ({ onFileSelect: e }) => {
    const [t, n] = N.useState(false), [r, i] = N.useState(null), o = N.useCallback((c) => {
      c.preventDefault(), c.stopPropagation(), n(true);
    }, []), a = N.useCallback((c) => {
      c.preventDefault(), c.stopPropagation(), n(false);
    }, []), s = N.useCallback((c) => {
      c.preventDefault(), c.stopPropagation(), n(false);
      const h = c.dataTransfer.files;
      if (h.length > 0) {
        const f = h[0];
        f.name.endsWith(".zip") ? (e(f), i(null)) : i("Please drop a .zip file");
      }
    }, [
      e
    ]), l = N.useCallback((c) => {
      const h = c.target.files;
      if (h && h.length > 0) {
        const f = h[0];
        f.name.endsWith(".zip") ? (e(f), i(null)) : i("Please select a .zip file");
      }
    }, [
      e
    ]);
    return q.jsxs("div", {
      className: "flex items-center justify-center min-h-screen p-8 bg-void",
      children: [
        q.jsxs("div", {
          className: "fixed inset-0 pointer-events-none",
          children: [
            q.jsx("div", {
              className: "absolute top-1/4 left-1/4 w-96 h-96 bg-accent/10 rounded-full blur-3xl"
            }),
            q.jsx("div", {
              className: "absolute bottom-1/4 right-1/4 w-96 h-96 bg-node-interface/10 rounded-full blur-3xl"
            })
          ]
        }),
        q.jsxs("div", {
          className: "relative w-full max-w-lg",
          children: [
            r && q.jsx("div", {
              className: "mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-sm text-center",
              children: r
            }),
            q.jsxs("div", {
              className: `
            relative p-16
            bg-surface border-2 border-dashed rounded-3xl
            transition-all duration-300 cursor-pointer
            ${t ? "border-accent bg-elevated scale-105 shadow-glow" : "border-border-default hover:border-accent/50 hover:bg-elevated/50 animate-breathe"}
          `,
              onDragOver: o,
              onDragLeave: a,
              onDrop: s,
              onClick: () => {
                var _a2;
                return (_a2 = document.getElementById("file-input")) == null ? void 0 : _a2.click();
              },
              children: [
                q.jsx("input", {
                  id: "file-input",
                  type: "file",
                  accept: ".zip",
                  className: "hidden",
                  onChange: l
                }),
                q.jsx("div", {
                  className: `
            mx-auto w-20 h-20 mb-6
            flex items-center justify-center
            bg-gradient-to-br from-accent to-node-interface
            rounded-2xl shadow-glow
            transition-transform duration-300
            ${t ? "scale-110" : ""}
          `,
                  children: t ? q.jsx(I0, {
                    className: "w-10 h-10 text-white"
                  }) : q.jsx(T0, {
                    className: "w-10 h-10 text-white"
                  })
                }),
                q.jsx("h2", {
                  className: "text-xl font-semibold text-text-primary text-center mb-2",
                  children: t ? "\u62D6\u653E\u5230\u8FD9\u91CC\uFF01" : "\u62D6\u653E\u60A8\u7684\u4EE3\u7801\u5E93"
                }),
                q.jsx("p", {
                  className: "text-sm text-text-secondary text-center mb-6",
                  children: "\u5C06 .zip \u6587\u4EF6\u62D6\u62FD\u5230\u6B64\u5904\u4EE5\u751F\u6210\u77E5\u8BC6\u56FE\u8C31"
                }),
                q.jsx("div", {
                  className: "flex items-center justify-center gap-3 text-xs text-text-muted",
                  children: q.jsx("span", {
                    className: "px-3 py-1.5 bg-elevated border border-border-subtle rounded-md",
                    children: ".zip"
                  })
                })
              ]
            })
          ]
        })
      ]
    });
  }, N0 = ({ progress: e }) => q.jsxs("div", {
    className: "fixed inset-0 flex flex-col items-center justify-center bg-void z-50",
    children: [
      q.jsxs("div", {
        className: "absolute inset-0 pointer-events-none",
        children: [
          q.jsx("div", {
            className: "absolute top-1/3 left-1/3 w-96 h-96 bg-accent/10 rounded-full blur-3xl animate-pulse"
          }),
          q.jsx("div", {
            className: "absolute bottom-1/3 right-1/3 w-96 h-96 bg-node-interface/10 rounded-full blur-3xl animate-pulse"
          })
        ]
      }),
      q.jsxs("div", {
        className: "relative mb-10",
        children: [
          q.jsx("div", {
            className: "w-28 h-28 bg-gradient-to-br from-accent to-node-interface rounded-full animate-pulse-glow"
          }),
          q.jsx("div", {
            className: "absolute inset-0 w-28 h-28 bg-gradient-to-br from-accent to-node-interface rounded-full blur-xl opacity-50"
          })
        ]
      }),
      q.jsx("div", {
        className: "w-80 mb-4",
        children: q.jsx("div", {
          className: "h-1.5 bg-elevated rounded-full overflow-hidden",
          children: q.jsx("div", {
            className: "h-full bg-gradient-to-r from-accent to-node-interface rounded-full transition-all duration-300 ease-out",
            style: {
              width: `${e.percent}%`
            }
          })
        })
      }),
      q.jsxs("div", {
        className: "text-center",
        children: [
          q.jsxs("p", {
            className: "font-mono text-sm text-text-secondary mb-1",
            children: [
              e.message,
              q.jsx("span", {
                className: "animate-pulse",
                children: "|"
              })
            ]
          }),
          e.detail && q.jsx("p", {
            className: "font-mono text-xs text-text-muted truncate max-w-md",
            children: e.detail
          })
        ]
      }),
      e.stats && q.jsxs("div", {
        className: "mt-8 flex items-center gap-6 text-xs text-text-muted",
        children: [
          q.jsxs("div", {
            className: "flex items-center gap-2",
            children: [
              q.jsx("span", {
                className: "w-2 h-2 bg-node-file rounded-full"
              }),
              q.jsxs("span", {
                children: [
                  e.stats.filesProcessed,
                  " / ",
                  e.stats.totalFiles,
                  " files"
                ]
              })
            ]
          }),
          q.jsxs("div", {
            className: "flex items-center gap-2",
            children: [
              q.jsx("span", {
                className: "w-2 h-2 bg-node-function rounded-full"
              }),
              q.jsxs("span", {
                children: [
                  e.stats.nodesCreated,
                  " nodes"
                ]
              })
            ]
          })
        ]
      }),
      q.jsxs("p", {
        className: "mt-4 font-mono text-3xl font-semibold text-text-primary",
        children: [
          e.percent,
          "%"
        ]
      })
    ]
  });
  function z0(e, t) {
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
    var t = z0(e, "string");
    return typeof t == "symbol" ? t : t + "";
  }
  function xt(e, t) {
    if (!(e instanceof t)) throw new TypeError("Cannot call a class as a function");
  }
  function Ud(e, t) {
    for (var n = 0; n < t.length; n++) {
      var r = t[n];
      r.enumerable = r.enumerable || false, r.configurable = true, "value" in r && (r.writable = true), Object.defineProperty(e, ao(r.key), r);
    }
  }
  function Tt(e, t, n) {
    return t && Ud(e.prototype, t), n && Ud(e, n), Object.defineProperty(e, "prototype", {
      writable: false
    }), e;
  }
  function gi(e) {
    return gi = Object.setPrototypeOf ? Object.getPrototypeOf.bind() : function(t) {
      return t.__proto__ || Object.getPrototypeOf(t);
    }, gi(e);
  }
  function Qp() {
    try {
      var e = !Boolean.prototype.valueOf.call(Reflect.construct(Boolean, [], function() {
      }));
    } catch {
    }
    return (Qp = function() {
      return !!e;
    })();
  }
  function O0(e) {
    if (e === void 0) throw new ReferenceError("this hasn't been initialised - super() hasn't been called");
    return e;
  }
  function G0(e, t) {
    if (t && (typeof t == "object" || typeof t == "function")) return t;
    if (t !== void 0) throw new TypeError("Derived constructors may only return object or undefined");
    return O0(e);
  }
  function an(e, t, n) {
    return t = gi(t), G0(e, Qp() ? Reflect.construct(t, n || [], gi(e).constructor) : t.apply(e, n));
  }
  function uu(e, t) {
    return uu = Object.setPrototypeOf ? Object.setPrototypeOf.bind() : function(n, r) {
      return n.__proto__ = r, n;
    }, uu(e, t);
  }
  function sn(e, t) {
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
  function U0(e) {
    if (Array.isArray(e)) return e;
  }
  function B0(e, t) {
    var n = e == null ? null : typeof Symbol < "u" && e[Symbol.iterator] || e["@@iterator"];
    if (n != null) {
      var r, i, o, a, s = [], l = true, c = false;
      try {
        if (o = (n = n.call(e)).next, t === 0) {
          if (Object(n) !== n) return;
          l = false;
        } else for (; !(l = (r = o.call(n)).done) && (s.push(r.value), s.length !== t); l = true) ;
      } catch (h) {
        c = true, i = h;
      } finally {
        try {
          if (!l && n.return != null && (a = n.return(), Object(a) !== a)) return;
        } finally {
          if (c) throw i;
        }
      }
      return s;
    }
  }
  function cu(e, t) {
    (t == null || t > e.length) && (t = e.length);
    for (var n = 0, r = Array(t); n < t; n++) r[n] = e[n];
    return r;
  }
  function Xp(e, t) {
    if (e) {
      if (typeof e == "string") return cu(e, t);
      var n = {}.toString.call(e).slice(8, -1);
      return n === "Object" && e.constructor && (n = e.constructor.name), n === "Map" || n === "Set" ? Array.from(e) : n === "Arguments" || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(n) ? cu(e, t) : void 0;
    }
  }
  function M0() {
    throw new TypeError(`Invalid attempt to destructure non-iterable instance.
In order to be iterable, non-array objects must have a [Symbol.iterator]() method.`);
  }
  function mi(e, t) {
    return U0(e) || B0(e, t) || Xp(e, t) || M0();
  }
  var el = {
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
  }, Zp = new Int8Array(4), tl = new Int32Array(Zp.buffer, 0, 1), $0 = new Float32Array(Zp.buffer, 0, 1), j0 = /^\s*rgba?\s*\(/, H0 = /^\s*rgba?\s*\(\s*([0-9]*)\s*,\s*([0-9]*)\s*,\s*([0-9]*)(?:\s*,\s*(.*)?)?\)\s*$/;
  function W0(e) {
    var t = 0, n = 0, r = 0, i = 1;
    if (e[0] === "#") e.length === 4 ? (t = parseInt(e.charAt(1) + e.charAt(1), 16), n = parseInt(e.charAt(2) + e.charAt(2), 16), r = parseInt(e.charAt(3) + e.charAt(3), 16)) : (t = parseInt(e.charAt(1) + e.charAt(2), 16), n = parseInt(e.charAt(3) + e.charAt(4), 16), r = parseInt(e.charAt(5) + e.charAt(6), 16)), e.length === 9 && (i = parseInt(e.charAt(7) + e.charAt(8), 16) / 255);
    else if (j0.test(e)) {
      var o = e.match(H0);
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
  for (var ea in el) ai[ea] = Si(el[ea]), ai[el[ea]] = ai[ea];
  function qp(e, t, n, r, i) {
    return tl[0] = r << 24 | n << 16 | t << 8 | e, tl[0] = tl[0] & 4278190079, $0[0];
  }
  function Si(e) {
    if (e = e.toLowerCase(), typeof ai[e] < "u") return ai[e];
    var t = W0(e), n = t.r, r = t.g, i = t.b, o = t.a;
    o = o * 255 | 0;
    var a = qp(n, r, i, o);
    return ai[e] = a, a;
  }
  var nl = {};
  function Jp(e) {
    if (typeof nl[e] < "u") return nl[e];
    var t = (e & 16711680) >>> 16, n = (e & 65280) >>> 8, r = e & 255, i = 255, o = qp(t, n, r, i);
    return nl[e] = o, o;
  }
  function Bd(e, t, n, r) {
    return n + (t << 8) + (e << 16);
  }
  function Md(e, t, n, r, i, o) {
    var a = Math.floor(n / o * i), s = Math.floor(e.drawingBufferHeight / o - r / o * i), l = new Uint8Array(4);
    e.bindFramebuffer(e.FRAMEBUFFER, t), e.readPixels(a, s, 1, 1, e.RGBA, e.UNSIGNED_BYTE, l);
    var c = mi(l, 4), h = c[0], f = c[1], p = c[2], y = c[3];
    return [
      h,
      f,
      p,
      y
    ];
  }
  function M(e, t, n) {
    return (t = ao(t)) in e ? Object.defineProperty(e, t, {
      value: n,
      enumerable: true,
      configurable: true,
      writable: true
    }) : e[t] = n, e;
  }
  function $d(e, t) {
    var n = Object.keys(e);
    if (Object.getOwnPropertySymbols) {
      var r = Object.getOwnPropertySymbols(e);
      t && (r = r.filter(function(i) {
        return Object.getOwnPropertyDescriptor(e, i).enumerable;
      })), n.push.apply(n, r);
    }
    return n;
  }
  function ee(e) {
    for (var t = 1; t < arguments.length; t++) {
      var n = arguments[t] != null ? arguments[t] : {};
      t % 2 ? $d(Object(n), true).forEach(function(r) {
        M(e, r, n[r]);
      }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(n)) : $d(Object(n)).forEach(function(r) {
        Object.defineProperty(e, r, Object.getOwnPropertyDescriptor(n, r));
      });
    }
    return e;
  }
  function V0(e, t) {
    for (; !{}.hasOwnProperty.call(e, t) && (e = gi(e)) !== null; ) ;
    return e;
  }
  function du() {
    return du = typeof Reflect < "u" && Reflect.get ? Reflect.get.bind() : function(e, t, n) {
      var r = V0(e, t);
      if (r) {
        var i = Object.getOwnPropertyDescriptor(r, t);
        return i.get ? i.get.call(arguments.length < 3 ? e : n) : i.value;
      }
    }, du.apply(null, arguments);
  }
  function eg(e, t, n, r) {
    var i = du(gi(e.prototype), t, n);
    return typeof i == "function" ? function(o) {
      return i.apply(n, o);
    } : i;
  }
  function K0(e) {
    return e.normalized ? 1 : e.size;
  }
  function rl(e) {
    var t = 0;
    return e.forEach(function(n) {
      return t += K0(n);
    }), t;
  }
  function tg(e, t, n) {
    var r = e === "VERTEX" ? t.VERTEX_SHADER : t.FRAGMENT_SHADER, i = t.createShader(r);
    if (i === null) throw new Error("loadShader: error while creating the shader");
    t.shaderSource(i, n), t.compileShader(i);
    var o = t.getShaderParameter(i, t.COMPILE_STATUS);
    if (!o) {
      var a = t.getShaderInfoLog(i);
      throw t.deleteShader(i), new Error(`loadShader: error while compiling the shader:
`.concat(a, `
`).concat(n));
    }
    return i;
  }
  function Y0(e, t) {
    return tg("VERTEX", e, t);
  }
  function Q0(e, t) {
    return tg("FRAGMENT", e, t);
  }
  function X0(e, t) {
    var n = e.createProgram();
    if (n === null) throw new Error("loadProgram: error while creating the program.");
    var r, i;
    for (r = 0, i = t.length; r < i; r++) e.attachShader(n, t[r]);
    e.linkProgram(n);
    var o = e.getProgramParameter(n, e.LINK_STATUS);
    if (!o) throw e.deleteProgram(n), new Error("loadProgram: error while linking the program.");
    return n;
  }
  function jd(e) {
    var t = e.gl, n = e.buffer, r = e.program, i = e.vertexShader, o = e.fragmentShader;
    t.deleteShader(i), t.deleteShader(o), t.deleteProgram(r), t.deleteBuffer(n);
  }
  var Hd = `#define PICKING_MODE
`, Z0 = M(M(M(M(M(M(M(M({}, WebGL2RenderingContext.BOOL, 1), WebGL2RenderingContext.BYTE, 1), WebGL2RenderingContext.UNSIGNED_BYTE, 1), WebGL2RenderingContext.SHORT, 2), WebGL2RenderingContext.UNSIGNED_SHORT, 2), WebGL2RenderingContext.INT, 4), WebGL2RenderingContext.UNSIGNED_INT, 4), WebGL2RenderingContext.FLOAT, 4), ng = function() {
    function e(t, n, r) {
      xt(this, e), M(this, "array", new Float32Array()), M(this, "constantArray", new Float32Array()), M(this, "capacity", 0), M(this, "verticesCount", 0);
      var i = this.getDefinition();
      if (this.VERTICES = i.VERTICES, this.VERTEX_SHADER_SOURCE = i.VERTEX_SHADER_SOURCE, this.FRAGMENT_SHADER_SOURCE = i.FRAGMENT_SHADER_SOURCE, this.UNIFORMS = i.UNIFORMS, this.ATTRIBUTES = i.ATTRIBUTES, this.METHOD = i.METHOD, this.CONSTANT_ATTRIBUTES = "CONSTANT_ATTRIBUTES" in i ? i.CONSTANT_ATTRIBUTES : [], this.CONSTANT_DATA = "CONSTANT_DATA" in i ? i.CONSTANT_DATA : [], this.isInstanced = "CONSTANT_ATTRIBUTES" in i, this.ATTRIBUTES_ITEMS_COUNT = rl(this.ATTRIBUTES), this.STRIDE = this.VERTICES * this.ATTRIBUTES_ITEMS_COUNT, this.renderer = r, this.normalProgram = this.getProgramInfo("normal", t, i.VERTEX_SHADER_SOURCE, i.FRAGMENT_SHADER_SOURCE, null), this.pickProgram = n ? this.getProgramInfo("pick", t, Hd + i.VERTEX_SHADER_SOURCE, Hd + i.FRAGMENT_SHADER_SOURCE, n) : null, this.isInstanced) {
        var o = rl(this.CONSTANT_ATTRIBUTES);
        if (this.CONSTANT_DATA.length !== this.VERTICES) throw new Error("Program: error while getting constant data (expected ".concat(this.VERTICES, " items, received ").concat(this.CONSTANT_DATA.length, " instead)"));
        this.constantArray = new Float32Array(this.CONSTANT_DATA.length * o);
        for (var a = 0; a < this.CONSTANT_DATA.length; a++) {
          var s = this.CONSTANT_DATA[a];
          if (s.length !== o) throw new Error("Program: error while getting constant data (one vector has ".concat(s.length, " items instead of ").concat(o, ")"));
          for (var l = 0; l < s.length; l++) this.constantArray[a * o + l] = s[l];
        }
        this.STRIDE = this.ATTRIBUTES_ITEMS_COUNT;
      }
    }
    return Tt(e, [
      {
        key: "kill",
        value: function() {
          jd(this.normalProgram), this.pickProgram && (jd(this.pickProgram), this.pickProgram = null);
        }
      },
      {
        key: "getProgramInfo",
        value: function(n, r, i, o, a) {
          var s = this.getDefinition(), l = r.createBuffer();
          if (l === null) throw new Error("Program: error while creating the WebGL buffer.");
          var c = Y0(r, i), h = Q0(r, o), f = X0(r, [
            c,
            h
          ]), p = {};
          s.UNIFORMS.forEach(function(b) {
            var I = r.getUniformLocation(f, b);
            I && (p[b] = I);
          });
          var y = {};
          s.ATTRIBUTES.forEach(function(b) {
            y[b.name] = r.getAttribLocation(f, b.name);
          });
          var k;
          if ("CONSTANT_ATTRIBUTES" in s && (s.CONSTANT_ATTRIBUTES.forEach(function(b) {
            y[b.name] = r.getAttribLocation(f, b.name);
          }), k = r.createBuffer(), k === null)) throw new Error("Program: error while creating the WebGL constant buffer.");
          return {
            name: n,
            program: f,
            gl: r,
            frameBuffer: a,
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
          var r = this, i = 0, o = n.gl, a = n.buffer;
          this.isInstanced ? (o.bindBuffer(o.ARRAY_BUFFER, n.constantBuffer), i = 0, this.CONSTANT_ATTRIBUTES.forEach(function(s) {
            return i += r.bindAttribute(s, n, i, false);
          }), o.bufferData(o.ARRAY_BUFFER, this.constantArray, o.STATIC_DRAW), o.bindBuffer(o.ARRAY_BUFFER, n.buffer), i = 0, this.ATTRIBUTES.forEach(function(s) {
            return i += r.bindAttribute(s, n, i, true);
          }), o.bufferData(o.ARRAY_BUFFER, this.array, o.DYNAMIC_DRAW)) : (o.bindBuffer(o.ARRAY_BUFFER, a), i = 0, this.ATTRIBUTES.forEach(function(s) {
            return i += r.bindAttribute(s, n, i);
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
          var a = Z0[n.type];
          if (typeof a != "number") throw new Error('Program.bind: yet unsupported attribute type "'.concat(n.type, '"'));
          var s = r.attributeLocations[n.name], l = r.gl;
          if (s !== -1) {
            l.enableVertexAttribArray(s);
            var c = this.isInstanced ? (o ? this.ATTRIBUTES_ITEMS_COUNT : rl(this.CONSTANT_ATTRIBUTES)) * Float32Array.BYTES_PER_ELEMENT : this.ATTRIBUTES_ITEMS_COUNT * Float32Array.BYTES_PER_ELEMENT;
            if (l.vertexAttribPointer(s, n.size, n.type, n.normalized || false, c, i), this.isInstanced && o) if (l instanceof WebGL2RenderingContext) l.vertexAttribDivisor(s, 1);
            else {
              var h = l.getExtension("ANGLE_instanced_arrays");
              h && h.vertexAttribDivisorANGLE(s, 1);
            }
          }
          return n.size * a;
        }
      },
      {
        key: "unbindAttribute",
        value: function(n, r, i) {
          var o = r.attributeLocations[n.name], a = r.gl;
          if (o !== -1 && (a.disableVertexAttribArray(o), this.isInstanced && i)) if (a instanceof WebGL2RenderingContext) a.vertexAttribDivisor(o, 0);
          else {
            var s = a.getExtension("ANGLE_instanced_arrays");
            s && s.vertexAttribDivisorANGLE(o, 0);
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
          this.hasNothingToRender() || (this.pickProgram && (this.pickProgram.gl.viewport(0, 0, n.width * n.pixelRatio / n.downSizingRatio, n.height * n.pixelRatio / n.downSizingRatio), this.bindProgram(this.pickProgram), this.renderProgram(ee(ee({}, n), {}, {
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
            var a = i.getExtension("ANGLE_instanced_arrays");
            a && a.drawArraysInstancedANGLE(n, 0, this.VERTICES, this.capacity);
          }
        }
      }
    ]);
  }(), q0 = function(e) {
    function t() {
      return xt(this, t), an(this, t, arguments);
    }
    return sn(t, e), Tt(t, [
      {
        key: "kill",
        value: function() {
          eg(t, "kill", this)([]);
        }
      },
      {
        key: "process",
        value: function(r, i, o) {
          var a = i * this.STRIDE;
          if (o.hidden) {
            for (var s = a + this.STRIDE; a < s; a++) this.array[a] = 0;
            return;
          }
          return this.processVisibleItem(Jp(r), a, o);
        }
      }
    ]);
  }(ng), vs = function(e) {
    function t() {
      var n;
      xt(this, t);
      for (var r = arguments.length, i = new Array(r), o = 0; o < r; o++) i[o] = arguments[o];
      return n = an(this, t, [].concat(i)), M(n, "drawLabel", void 0), n;
    }
    return sn(t, e), Tt(t, [
      {
        key: "kill",
        value: function() {
          eg(t, "kill", this)([]);
        }
      },
      {
        key: "process",
        value: function(r, i, o, a, s) {
          var l = i * this.STRIDE;
          if (s.hidden || o.hidden || a.hidden) {
            for (var c = l + this.STRIDE; l < c; l++) this.array[l] = 0;
            return;
          }
          return this.processVisibleItem(Jp(r), l, o, a, s);
        }
      }
    ]);
  }(ng);
  function J0(e, t) {
    return function() {
      function n(r, i, o) {
        xt(this, n), M(this, "drawLabel", t), this.programs = e.map(function(a) {
          return new a(r, i, o);
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
          value: function(i, o, a, s, l) {
            this.programs.forEach(function(c) {
              return c.process(i, o, a, s, l);
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
  function ew(e, t, n, r, i) {
    var o = i.edgeLabelSize, a = i.edgeLabelFont, s = i.edgeLabelWeight, l = i.edgeLabelColor.attribute ? t[i.edgeLabelColor.attribute] || i.edgeLabelColor.color || "#000" : i.edgeLabelColor.color, c = t.label;
    if (c) {
      e.fillStyle = l, e.font = "".concat(s, " ").concat(o, "px ").concat(a);
      var h = n.size, f = r.size, p = n.x, y = n.y, k = r.x, b = r.y, I = (p + k) / 2, S = (y + b) / 2, m = k - p, v = b - y, E = Math.sqrt(m * m + v * v);
      if (!(E < h + f)) {
        p += m * h / E, y += v * h / E, k -= m * f / E, b -= v * f / E, I = (p + k) / 2, S = (y + b) / 2, m = k - p, v = b - y, E = Math.sqrt(m * m + v * v);
        var A = e.measureText(c).width;
        if (A > E) {
          var F = "\u2026";
          for (c = c + F, A = e.measureText(c).width; A > E && c.length > 1; ) c = c.slice(0, -2) + F, A = e.measureText(c).width;
          if (c.length < 4) return;
        }
        var R;
        m > 0 ? v > 0 ? R = Math.acos(m / E) : R = Math.asin(v / E) : v > 0 ? R = Math.acos(m / E) + Math.PI : R = Math.asin(m / E) + Math.PI / 2, e.save(), e.translate(I, S), e.rotate(R), e.fillText(c, -A / 2, t.size / 2 + o), e.restore();
      }
    }
  }
  function rg(e, t, n) {
    if (t.label) {
      var r = n.labelSize, i = n.labelFont, o = n.labelWeight, a = n.labelColor.attribute ? t[n.labelColor.attribute] || n.labelColor.color || "#000" : n.labelColor.color;
      e.fillStyle = a, e.font = "".concat(o, " ").concat(r, "px ").concat(i), e.fillText(t.label, t.x + t.size + 3, t.y + r / 3);
    }
  }
  function tw(e, t, n) {
    var r = n.labelSize, i = n.labelFont, o = n.labelWeight;
    e.font = "".concat(o, " ").concat(r, "px ").concat(i), e.fillStyle = "#FFF", e.shadowOffsetX = 0, e.shadowOffsetY = 0, e.shadowBlur = 8, e.shadowColor = "#000";
    var a = 2;
    if (typeof t.label == "string") {
      var s = e.measureText(t.label).width, l = Math.round(s + 5), c = Math.round(r + 2 * a), h = Math.max(t.size, r / 2) + a, f = Math.asin(c / 2 / h), p = Math.sqrt(Math.abs(Math.pow(h, 2) - Math.pow(c / 2, 2)));
      e.beginPath(), e.moveTo(t.x + p, t.y + c / 2), e.lineTo(t.x + h + l, t.y + c / 2), e.lineTo(t.x + h + l, t.y - c / 2), e.lineTo(t.x + p, t.y - c / 2), e.arc(t.x, t.y, h, f, -f), e.closePath(), e.fill();
    } else e.beginPath(), e.arc(t.x, t.y, t.size + a, 0, Math.PI * 2), e.closePath(), e.fill();
    e.shadowOffsetX = 0, e.shadowOffsetY = 0, e.shadowBlur = 0, rg(e, t, n);
  }
  var nw = `
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
`, rw = nw, iw = `
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
`, ow = iw, ig = WebGLRenderingContext, Wd = ig.UNSIGNED_BYTE, il = ig.FLOAT, aw = [
    "u_sizeRatio",
    "u_correctionRatio",
    "u_matrix"
  ], ys = function(e) {
    function t() {
      return xt(this, t), an(this, t, arguments);
    }
    return sn(t, e), Tt(t, [
      {
        key: "getDefinition",
        value: function() {
          return {
            VERTICES: 3,
            VERTEX_SHADER_SOURCE: ow,
            FRAGMENT_SHADER_SOURCE: rw,
            METHOD: WebGLRenderingContext.TRIANGLES,
            UNIFORMS: aw,
            ATTRIBUTES: [
              {
                name: "a_position",
                size: 2,
                type: il
              },
              {
                name: "a_size",
                size: 1,
                type: il
              },
              {
                name: "a_color",
                size: 4,
                type: Wd,
                normalized: true
              },
              {
                name: "a_id",
                size: 4,
                type: Wd,
                normalized: true
              }
            ],
            CONSTANT_ATTRIBUTES: [
              {
                name: "a_angle",
                size: 1,
                type: il
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
          var a = this.array, s = Si(o.color);
          a[i++] = o.x, a[i++] = o.y, a[i++] = o.size, a[i++] = s, a[i++] = r;
        }
      },
      {
        key: "setUniforms",
        value: function(r, i) {
          var o = i.gl, a = i.uniformLocations, s = a.u_sizeRatio, l = a.u_correctionRatio, c = a.u_matrix;
          o.uniform1f(l, r.correctionRatio), o.uniform1f(s, r.sizeRatio), o.uniformMatrix3fv(c, false, r.matrix);
        }
      }
    ]);
  }(q0);
  M(ys, "ANGLE_1", 0);
  M(ys, "ANGLE_2", 2 * Math.PI / 3);
  M(ys, "ANGLE_3", 4 * Math.PI / 3);
  var sw = `
precision mediump float;

varying vec4 v_color;

void main(void) {
  gl_FragColor = v_color;
}
`, lw = sw, uw = `
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
`, cw = uw, og = WebGLRenderingContext, Vd = og.UNSIGNED_BYTE, ta = og.FLOAT, dw = [
    "u_matrix",
    "u_sizeRatio",
    "u_correctionRatio",
    "u_minEdgeThickness",
    "u_lengthToThicknessRatio",
    "u_widenessToThicknessRatio"
  ], ws = {
    extremity: "target",
    lengthToThicknessRatio: 2.5,
    widenessToThicknessRatio: 2
  };
  function ag(e) {
    var t = ee(ee({}, ws), {});
    return function(n) {
      function r() {
        return xt(this, r), an(this, r, arguments);
      }
      return sn(r, n), Tt(r, [
        {
          key: "getDefinition",
          value: function() {
            return {
              VERTICES: 3,
              VERTEX_SHADER_SOURCE: cw,
              FRAGMENT_SHADER_SOURCE: lw,
              METHOD: WebGLRenderingContext.TRIANGLES,
              UNIFORMS: dw,
              ATTRIBUTES: [
                {
                  name: "a_position",
                  size: 2,
                  type: ta
                },
                {
                  name: "a_normal",
                  size: 2,
                  type: ta
                },
                {
                  name: "a_radius",
                  size: 1,
                  type: ta
                },
                {
                  name: "a_color",
                  size: 4,
                  type: Vd,
                  normalized: true
                },
                {
                  name: "a_id",
                  size: 4,
                  type: Vd,
                  normalized: true
                }
              ],
              CONSTANT_ATTRIBUTES: [
                {
                  name: "a_barycentric",
                  size: 3,
                  type: ta
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
          value: function(o, a, s, l, c) {
            if (t.extremity === "source") {
              var h = [
                l,
                s
              ];
              s = h[0], l = h[1];
            }
            var f = c.size || 1, p = l.size || 1, y = s.x, k = s.y, b = l.x, I = l.y, S = Si(c.color), m = b - y, v = I - k, E = m * m + v * v, A = 0, F = 0;
            E && (E = 1 / Math.sqrt(E), A = -v * E * f, F = m * E * f);
            var R = this.array;
            R[a++] = b, R[a++] = I, R[a++] = -A, R[a++] = -F, R[a++] = p, R[a++] = S, R[a++] = o;
          }
        },
        {
          key: "setUniforms",
          value: function(o, a) {
            var s = a.gl, l = a.uniformLocations, c = l.u_matrix, h = l.u_sizeRatio, f = l.u_correctionRatio, p = l.u_minEdgeThickness, y = l.u_lengthToThicknessRatio, k = l.u_widenessToThicknessRatio;
            s.uniformMatrix3fv(c, false, o.matrix), s.uniform1f(h, o.sizeRatio), s.uniform1f(f, o.correctionRatio), s.uniform1f(p, o.minEdgeThickness), s.uniform1f(y, t.lengthToThicknessRatio), s.uniform1f(k, t.widenessToThicknessRatio);
          }
        }
      ]);
    }(vs);
  }
  ag();
  var fw = `
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
`, sg = fw, hw = `
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
`, pw = hw, lg = WebGLRenderingContext, Kd = lg.UNSIGNED_BYTE, Sr = lg.FLOAT, gw = [
    "u_matrix",
    "u_zoomRatio",
    "u_sizeRatio",
    "u_correctionRatio",
    "u_pixelRatio",
    "u_feather",
    "u_minEdgeThickness",
    "u_lengthToThicknessRatio"
  ], mw = {
    lengthToThicknessRatio: ws.lengthToThicknessRatio
  };
  function ug(e) {
    var t = ee(ee({}, mw), {});
    return function(n) {
      function r() {
        return xt(this, r), an(this, r, arguments);
      }
      return sn(r, n), Tt(r, [
        {
          key: "getDefinition",
          value: function() {
            return {
              VERTICES: 6,
              VERTEX_SHADER_SOURCE: pw,
              FRAGMENT_SHADER_SOURCE: sg,
              METHOD: WebGLRenderingContext.TRIANGLES,
              UNIFORMS: gw,
              ATTRIBUTES: [
                {
                  name: "a_positionStart",
                  size: 2,
                  type: Sr
                },
                {
                  name: "a_positionEnd",
                  size: 2,
                  type: Sr
                },
                {
                  name: "a_normal",
                  size: 2,
                  type: Sr
                },
                {
                  name: "a_color",
                  size: 4,
                  type: Kd,
                  normalized: true
                },
                {
                  name: "a_id",
                  size: 4,
                  type: Kd,
                  normalized: true
                },
                {
                  name: "a_radius",
                  size: 1,
                  type: Sr
                }
              ],
              CONSTANT_ATTRIBUTES: [
                {
                  name: "a_positionCoef",
                  size: 1,
                  type: Sr
                },
                {
                  name: "a_normalCoef",
                  size: 1,
                  type: Sr
                },
                {
                  name: "a_radiusCoef",
                  size: 1,
                  type: Sr
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
          value: function(o, a, s, l, c) {
            var h = c.size || 1, f = s.x, p = s.y, y = l.x, k = l.y, b = Si(c.color), I = y - f, S = k - p, m = l.size || 1, v = I * I + S * S, E = 0, A = 0;
            v && (v = 1 / Math.sqrt(v), E = -S * v * h, A = I * v * h);
            var F = this.array;
            F[a++] = f, F[a++] = p, F[a++] = y, F[a++] = k, F[a++] = E, F[a++] = A, F[a++] = b, F[a++] = o, F[a++] = m;
          }
        },
        {
          key: "setUniforms",
          value: function(o, a) {
            var s = a.gl, l = a.uniformLocations, c = l.u_matrix, h = l.u_zoomRatio, f = l.u_feather, p = l.u_pixelRatio, y = l.u_correctionRatio, k = l.u_sizeRatio, b = l.u_minEdgeThickness, I = l.u_lengthToThicknessRatio;
            s.uniformMatrix3fv(c, false, o.matrix), s.uniform1f(h, o.zoomRatio), s.uniform1f(k, o.sizeRatio), s.uniform1f(y, o.correctionRatio), s.uniform1f(p, o.pixelRatio), s.uniform1f(f, o.antiAliasingFeather), s.uniform1f(b, o.minEdgeThickness), s.uniform1f(I, t.lengthToThicknessRatio);
          }
        }
      ]);
    }(vs);
  }
  ug();
  function vw(e) {
    return J0([
      ug(),
      ag()
    ]);
  }
  var yw = vw(), ww = yw, Ew = `
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
`, Sw = Ew, cg = WebGLRenderingContext, Yd = cg.UNSIGNED_BYTE, zi = cg.FLOAT, _w = [
    "u_matrix",
    "u_zoomRatio",
    "u_sizeRatio",
    "u_correctionRatio",
    "u_pixelRatio",
    "u_feather",
    "u_minEdgeThickness"
  ], kw = function(e) {
    function t() {
      return xt(this, t), an(this, t, arguments);
    }
    return sn(t, e), Tt(t, [
      {
        key: "getDefinition",
        value: function() {
          return {
            VERTICES: 6,
            VERTEX_SHADER_SOURCE: Sw,
            FRAGMENT_SHADER_SOURCE: sg,
            METHOD: WebGLRenderingContext.TRIANGLES,
            UNIFORMS: _w,
            ATTRIBUTES: [
              {
                name: "a_positionStart",
                size: 2,
                type: zi
              },
              {
                name: "a_positionEnd",
                size: 2,
                type: zi
              },
              {
                name: "a_normal",
                size: 2,
                type: zi
              },
              {
                name: "a_color",
                size: 4,
                type: Yd,
                normalized: true
              },
              {
                name: "a_id",
                size: 4,
                type: Yd,
                normalized: true
              }
            ],
            CONSTANT_ATTRIBUTES: [
              {
                name: "a_positionCoef",
                size: 1,
                type: zi
              },
              {
                name: "a_normalCoef",
                size: 1,
                type: zi
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
        value: function(r, i, o, a, s) {
          var l = s.size || 1, c = o.x, h = o.y, f = a.x, p = a.y, y = Si(s.color), k = f - c, b = p - h, I = k * k + b * b, S = 0, m = 0;
          I && (I = 1 / Math.sqrt(I), S = -b * I * l, m = k * I * l);
          var v = this.array;
          v[i++] = c, v[i++] = h, v[i++] = f, v[i++] = p, v[i++] = S, v[i++] = m, v[i++] = y, v[i++] = r;
        }
      },
      {
        key: "setUniforms",
        value: function(r, i) {
          var o = i.gl, a = i.uniformLocations, s = a.u_matrix, l = a.u_zoomRatio, c = a.u_feather, h = a.u_pixelRatio, f = a.u_correctionRatio, p = a.u_sizeRatio, y = a.u_minEdgeThickness;
          o.uniformMatrix3fv(s, false, r.matrix), o.uniform1f(l, r.zoomRatio), o.uniform1f(p, r.sizeRatio), o.uniform1f(f, r.correctionRatio), o.uniform1f(h, r.pixelRatio), o.uniform1f(c, r.antiAliasingFeather), o.uniform1f(y, r.minEdgeThickness);
        }
      }
    ]);
  }(vs), dc = {
    exports: {}
  }, si = typeof Reflect == "object" ? Reflect : null, Qd = si && typeof si.apply == "function" ? si.apply : function(t, n, r) {
    return Function.prototype.apply.call(t, n, r);
  }, Sa;
  si && typeof si.ownKeys == "function" ? Sa = si.ownKeys : Object.getOwnPropertySymbols ? Sa = function(t) {
    return Object.getOwnPropertyNames(t).concat(Object.getOwnPropertySymbols(t));
  } : Sa = function(t) {
    return Object.getOwnPropertyNames(t);
  };
  function bw(e) {
    console && console.warn && console.warn(e);
  }
  var dg = Number.isNaN || function(t) {
    return t !== t;
  };
  function Fe() {
    Fe.init.call(this);
  }
  dc.exports = Fe;
  dc.exports.once = Rw;
  Fe.EventEmitter = Fe;
  Fe.prototype._events = void 0;
  Fe.prototype._eventsCount = 0;
  Fe.prototype._maxListeners = void 0;
  var Xd = 10;
  function Es(e) {
    if (typeof e != "function") throw new TypeError('The "listener" argument must be of type Function. Received type ' + typeof e);
  }
  Object.defineProperty(Fe, "defaultMaxListeners", {
    enumerable: true,
    get: function() {
      return Xd;
    },
    set: function(e) {
      if (typeof e != "number" || e < 0 || dg(e)) throw new RangeError('The value of "defaultMaxListeners" is out of range. It must be a non-negative number. Received ' + e + ".");
      Xd = e;
    }
  });
  Fe.init = function() {
    (this._events === void 0 || this._events === Object.getPrototypeOf(this)._events) && (this._events = /* @__PURE__ */ Object.create(null), this._eventsCount = 0), this._maxListeners = this._maxListeners || void 0;
  };
  Fe.prototype.setMaxListeners = function(t) {
    if (typeof t != "number" || t < 0 || dg(t)) throw new RangeError('The value of "n" is out of range. It must be a non-negative number. Received ' + t + ".");
    return this._maxListeners = t, this;
  };
  function fg(e) {
    return e._maxListeners === void 0 ? Fe.defaultMaxListeners : e._maxListeners;
  }
  Fe.prototype.getMaxListeners = function() {
    return fg(this);
  };
  Fe.prototype.emit = function(t) {
    for (var n = [], r = 1; r < arguments.length; r++) n.push(arguments[r]);
    var i = t === "error", o = this._events;
    if (o !== void 0) i = i && o.error === void 0;
    else if (!i) return false;
    if (i) {
      var a;
      if (n.length > 0 && (a = n[0]), a instanceof Error) throw a;
      var s = new Error("Unhandled error." + (a ? " (" + a.message + ")" : ""));
      throw s.context = a, s;
    }
    var l = o[t];
    if (l === void 0) return false;
    if (typeof l == "function") Qd(l, this, n);
    else for (var c = l.length, h = vg(l, c), r = 0; r < c; ++r) Qd(h[r], this, n);
    return true;
  };
  function hg(e, t, n, r) {
    var i, o, a;
    if (Es(n), o = e._events, o === void 0 ? (o = e._events = /* @__PURE__ */ Object.create(null), e._eventsCount = 0) : (o.newListener !== void 0 && (e.emit("newListener", t, n.listener ? n.listener : n), o = e._events), a = o[t]), a === void 0) a = o[t] = n, ++e._eventsCount;
    else if (typeof a == "function" ? a = o[t] = r ? [
      n,
      a
    ] : [
      a,
      n
    ] : r ? a.unshift(n) : a.push(n), i = fg(e), i > 0 && a.length > i && !a.warned) {
      a.warned = true;
      var s = new Error("Possible EventEmitter memory leak detected. " + a.length + " " + String(t) + " listeners added. Use emitter.setMaxListeners() to increase limit");
      s.name = "MaxListenersExceededWarning", s.emitter = e, s.type = t, s.count = a.length, bw(s);
    }
    return e;
  }
  Fe.prototype.addListener = function(t, n) {
    return hg(this, t, n, false);
  };
  Fe.prototype.on = Fe.prototype.addListener;
  Fe.prototype.prependListener = function(t, n) {
    return hg(this, t, n, true);
  };
  function Cw() {
    if (!this.fired) return this.target.removeListener(this.type, this.wrapFn), this.fired = true, arguments.length === 0 ? this.listener.call(this.target) : this.listener.apply(this.target, arguments);
  }
  function pg(e, t, n) {
    var r = {
      fired: false,
      wrapFn: void 0,
      target: e,
      type: t,
      listener: n
    }, i = Cw.bind(r);
    return i.listener = n, r.wrapFn = i, i;
  }
  Fe.prototype.once = function(t, n) {
    return Es(n), this.on(t, pg(this, t, n)), this;
  };
  Fe.prototype.prependOnceListener = function(t, n) {
    return Es(n), this.prependListener(t, pg(this, t, n)), this;
  };
  Fe.prototype.removeListener = function(t, n) {
    var r, i, o, a, s;
    if (Es(n), i = this._events, i === void 0) return this;
    if (r = i[t], r === void 0) return this;
    if (r === n || r.listener === n) --this._eventsCount === 0 ? this._events = /* @__PURE__ */ Object.create(null) : (delete i[t], i.removeListener && this.emit("removeListener", t, r.listener || n));
    else if (typeof r != "function") {
      for (o = -1, a = r.length - 1; a >= 0; a--) if (r[a] === n || r[a].listener === n) {
        s = r[a].listener, o = a;
        break;
      }
      if (o < 0) return this;
      o === 0 ? r.shift() : xw(r, o), r.length === 1 && (i[t] = r[0]), i.removeListener !== void 0 && this.emit("removeListener", t, s || n);
    }
    return this;
  };
  Fe.prototype.off = Fe.prototype.removeListener;
  Fe.prototype.removeAllListeners = function(t) {
    var n, r, i;
    if (r = this._events, r === void 0) return this;
    if (r.removeListener === void 0) return arguments.length === 0 ? (this._events = /* @__PURE__ */ Object.create(null), this._eventsCount = 0) : r[t] !== void 0 && (--this._eventsCount === 0 ? this._events = /* @__PURE__ */ Object.create(null) : delete r[t]), this;
    if (arguments.length === 0) {
      var o = Object.keys(r), a;
      for (i = 0; i < o.length; ++i) a = o[i], a !== "removeListener" && this.removeAllListeners(a);
      return this.removeAllListeners("removeListener"), this._events = /* @__PURE__ */ Object.create(null), this._eventsCount = 0, this;
    }
    if (n = r[t], typeof n == "function") this.removeListener(t, n);
    else if (n !== void 0) for (i = n.length - 1; i >= 0; i--) this.removeListener(t, n[i]);
    return this;
  };
  function gg(e, t, n) {
    var r = e._events;
    if (r === void 0) return [];
    var i = r[t];
    return i === void 0 ? [] : typeof i == "function" ? n ? [
      i.listener || i
    ] : [
      i
    ] : n ? Tw(i) : vg(i, i.length);
  }
  Fe.prototype.listeners = function(t) {
    return gg(this, t, true);
  };
  Fe.prototype.rawListeners = function(t) {
    return gg(this, t, false);
  };
  Fe.listenerCount = function(e, t) {
    return typeof e.listenerCount == "function" ? e.listenerCount(t) : mg.call(e, t);
  };
  Fe.prototype.listenerCount = mg;
  function mg(e) {
    var t = this._events;
    if (t !== void 0) {
      var n = t[e];
      if (typeof n == "function") return 1;
      if (n !== void 0) return n.length;
    }
    return 0;
  }
  Fe.prototype.eventNames = function() {
    return this._eventsCount > 0 ? Sa(this._events) : [];
  };
  function vg(e, t) {
    for (var n = new Array(t), r = 0; r < t; ++r) n[r] = e[r];
    return n;
  }
  function xw(e, t) {
    for (; t + 1 < e.length; t++) e[t] = e[t + 1];
    e.pop();
  }
  function Tw(e) {
    for (var t = new Array(e.length), n = 0; n < t.length; ++n) t[n] = e[n].listener || e[n];
    return t;
  }
  function Rw(e, t) {
    return new Promise(function(n, r) {
      function i(a) {
        e.removeListener(t, o), r(a);
      }
      function o() {
        typeof e.removeListener == "function" && e.removeListener("error", i), n([].slice.call(arguments));
      }
      yg(e, t, o, {
        once: true
      }), t !== "error" && Aw(e, i, {
        once: true
      });
    });
  }
  function Aw(e, t, n) {
    typeof e.on == "function" && yg(e, "error", t, n);
  }
  function yg(e, t, n, r) {
    if (typeof e.on == "function") r.once ? e.once(t, n) : e.on(t, n);
    else if (typeof e.addEventListener == "function") e.addEventListener(t, function i(o) {
      r.once && e.removeEventListener(t, i), n(o);
    });
    else throw new TypeError('The "emitter" argument must be of type EventEmitter. Received type ' + typeof e);
  }
  var wg = dc.exports, fc = function(e) {
    function t() {
      var n;
      return xt(this, t), n = an(this, t), n.rawEmitter = n, n;
    }
    return sn(t, e), Tt(t);
  }(wg.EventEmitter), Ss = function(t) {
    return t !== null && typeof t == "object" && typeof t.addUndirectedEdgeWithKey == "function" && typeof t.dropNode == "function" && typeof t.multi == "boolean";
  };
  const Lw = xo(Ss);
  var Dw = function(t) {
    return t;
  }, Pw = function(t) {
    return t * t;
  }, Iw = function(t) {
    return t * (2 - t);
  }, Fw = function(t) {
    return (t *= 2) < 1 ? 0.5 * t * t : -0.5 * (--t * (t - 2) - 1);
  }, Nw = function(t) {
    return t * t * t;
  }, zw = function(t) {
    return --t * t * t + 1;
  }, Ow = function(t) {
    return (t *= 2) < 1 ? 0.5 * t * t * t : 0.5 * ((t -= 2) * t * t + 2);
  }, Gw = {
    linear: Dw,
    quadraticIn: Pw,
    quadraticOut: Iw,
    quadraticInOut: Fw,
    cubicIn: Nw,
    cubicOut: zw,
    cubicInOut: Ow
  }, Uw = {
    easing: "quadraticInOut",
    duration: 150
  };
  function pn() {
    return Float32Array.of(1, 0, 0, 0, 1, 0, 0, 0, 1);
  }
  function na(e, t, n) {
    return e[0] = t, e[4] = typeof n == "number" ? n : t, e;
  }
  function Zd(e, t) {
    var n = Math.sin(t), r = Math.cos(t);
    return e[0] = r, e[1] = n, e[3] = -n, e[4] = r, e;
  }
  function qd(e, t, n) {
    return e[6] = t, e[7] = n, e;
  }
  function qn(e, t) {
    var n = e[0], r = e[1], i = e[2], o = e[3], a = e[4], s = e[5], l = e[6], c = e[7], h = e[8], f = t[0], p = t[1], y = t[2], k = t[3], b = t[4], I = t[5], S = t[6], m = t[7], v = t[8];
    return e[0] = f * n + p * o + y * l, e[1] = f * r + p * a + y * c, e[2] = f * i + p * s + y * h, e[3] = k * n + b * o + I * l, e[4] = k * r + b * a + I * c, e[5] = k * i + b * s + I * h, e[6] = S * n + m * o + v * l, e[7] = S * r + m * a + v * c, e[8] = S * i + m * s + v * h, e;
  }
  function fu(e, t) {
    var n = arguments.length > 2 && arguments[2] !== void 0 ? arguments[2] : 1, r = e[0], i = e[1], o = e[3], a = e[4], s = e[6], l = e[7], c = t.x, h = t.y;
    return {
      x: c * r + h * o + s * n,
      y: c * i + h * a + l * n
    };
  }
  function Bw(e, t) {
    var n = e.height / e.width, r = t.height / t.width;
    return n < 1 && r > 1 || n > 1 && r < 1 ? 1 : Math.min(Math.max(r, 1 / r), Math.max(1 / n, n));
  }
  function Oi(e, t, n, r, i) {
    var o = e.angle, a = e.ratio, s = e.x, l = e.y, c = t.width, h = t.height, f = pn(), p = Math.min(c, h) - 2 * r, y = Bw(t, n);
    return i ? (qn(f, qd(pn(), s, l)), qn(f, na(pn(), a)), qn(f, Zd(pn(), o)), qn(f, na(pn(), c / p / 2 / y, h / p / 2 / y))) : (qn(f, na(pn(), 2 * (p / c) * y, 2 * (p / h) * y)), qn(f, Zd(pn(), -o)), qn(f, na(pn(), 1 / a)), qn(f, qd(pn(), -s, -l))), f;
  }
  function Mw(e, t, n) {
    var r = fu(e, {
      x: Math.cos(t.angle),
      y: Math.sin(t.angle)
    }, 0), i = r.x, o = r.y;
    return 1 / Math.sqrt(Math.pow(i, 2) + Math.pow(o, 2)) / n.width;
  }
  function $w(e) {
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
    return e.forEachNode(function(o, a) {
      var s = a.x, l = a.y;
      s < t && (t = s), s > n && (n = s), l < r && (r = l), l > i && (i = l);
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
  function jw(e) {
    if (!Lw(e)) throw new Error("Sigma: invalid graph instance.");
    e.forEachNode(function(t, n) {
      if (!Number.isFinite(n.x) || !Number.isFinite(n.y)) throw new Error("Sigma: Coordinates of node ".concat(t, " are invalid. A node must have a numeric 'x' and 'y' attribute."));
    });
  }
  function Hw(e, t, n) {
    var r = document.createElement(e);
    if (t) for (var i in t) r.style[i] = t[i];
    if (n) for (var o in n) r.setAttribute(o, n[o]);
    return r;
  }
  function Jd() {
    return typeof window.devicePixelRatio < "u" ? window.devicePixelRatio : 1;
  }
  function ef(e, t, n) {
    return n.sort(function(r, i) {
      var o = t(r) || 0, a = t(i) || 0;
      return o < a ? -1 : o > a ? 1 : 0;
    });
  }
  function tf(e) {
    var t = mi(e.x, 2), n = t[0], r = t[1], i = mi(e.y, 2), o = i[0], a = i[1], s = Math.max(r - n, a - o), l = (r + n) / 2, c = (a + o) / 2;
    (s === 0 || Math.abs(s) === 1 / 0 || isNaN(s)) && (s = 1), isNaN(l) && (l = 0), isNaN(c) && (c = 0);
    var h = function(p) {
      return {
        x: 0.5 + (p.x - l) / s,
        y: 0.5 + (p.y - c) / s
      };
    };
    return h.applyTo = function(f) {
      f.x = 0.5 + (f.x - l) / s, f.y = 0.5 + (f.y - c) / s;
    }, h.inverse = function(f) {
      return {
        x: l + s * (f.x - 0.5),
        y: c + s * (f.y - 0.5)
      };
    }, h.ratio = s, h;
  }
  function hu(e) {
    "@babel/helpers - typeof";
    return hu = typeof Symbol == "function" && typeof Symbol.iterator == "symbol" ? function(t) {
      return typeof t;
    } : function(t) {
      return t && typeof Symbol == "function" && t.constructor === Symbol && t !== Symbol.prototype ? "symbol" : typeof t;
    }, hu(e);
  }
  function nf(e, t) {
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
  function ol(e) {
    e = e || {};
    for (var t = 0, n = arguments.length <= 1 ? 0 : arguments.length - 1; t < n; t++) {
      var r = t + 1 < 1 || arguments.length <= t + 1 ? void 0 : arguments[t + 1];
      r && Object.assign(e, r);
    }
    return e;
  }
  var hc = {
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
    defaultDrawEdgeLabel: ew,
    defaultDrawNodeLabel: rg,
    defaultDrawNodeHover: tw,
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
  }, Ww = {
    circle: ys
  }, Vw = {
    arrow: ww,
    line: kw
  };
  function al(e) {
    if (typeof e.labelDensity != "number" || e.labelDensity < 0) throw new Error("Settings: invalid `labelDensity`. Expecting a positive number.");
    var t = e.minCameraRatio, n = e.maxCameraRatio;
    if (typeof t == "number" && typeof n == "number" && n < t) throw new Error("Settings: invalid camera ratio boundaries. Expecting `maxCameraRatio` to be greater than `minCameraRatio`.");
  }
  function Kw(e) {
    var t = ol({}, hc, e);
    return t.nodeProgramClasses = ol({}, Ww, t.nodeProgramClasses), t.edgeProgramClasses = ol({}, Vw, t.edgeProgramClasses), t;
  }
  var ra = 1.5, rf = function(e) {
    function t() {
      var n;
      return xt(this, t), n = an(this, t), M(n, "x", 0.5), M(n, "y", 0.5), M(n, "angle", 0), M(n, "ratio", 1), M(n, "minRatio", null), M(n, "maxRatio", null), M(n, "enabledZooming", true), M(n, "enabledPanning", true), M(n, "enabledRotation", true), M(n, "clean", null), M(n, "nextFrame", null), M(n, "previousState", null), M(n, "enabled", true), n.previousState = n.getState(), n;
    }
    return sn(t, e), Tt(t, [
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
          return this.enabledPanning && typeof r.x == "number" && (i.x = r.x), this.enabledPanning && typeof r.y == "number" && (i.y = r.y), this.enabledZooming && typeof r.ratio == "number" && (i.ratio = this.getBoundedRatio(r.ratio)), this.enabledRotation && typeof r.angle == "number" && (i.angle = r.angle), this.clean ? this.clean(ee(ee({}, this.getState()), i)) : i;
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
          var i = this, o = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : {}, a = arguments.length > 2 ? arguments[2] : void 0;
          if (!a) return new Promise(function(y) {
            return i.animate(r, o, y);
          });
          if (this.enabled) {
            var s = ee(ee({}, Uw), o), l = this.validateState(r), c = typeof s.easing == "function" ? s.easing : Gw[s.easing], h = Date.now(), f = this.getState(), p = function() {
              var k = (Date.now() - h) / s.duration;
              if (k >= 1) {
                i.nextFrame = null, i.setState(l), i.animationCallback && (i.animationCallback.call(null), i.animationCallback = void 0);
                return;
              }
              var b = c(k), I = {};
              typeof l.x == "number" && (I.x = f.x + (l.x - f.x) * b), typeof l.y == "number" && (I.y = f.y + (l.y - f.y) * b), i.enabledRotation && typeof l.angle == "number" && (I.angle = f.angle + (l.angle - f.angle) * b), typeof l.ratio == "number" && (I.ratio = f.ratio + (l.ratio - f.ratio) * b), i.setState(I), i.nextFrame = requestAnimationFrame(p);
            };
            this.nextFrame ? (cancelAnimationFrame(this.nextFrame), this.animationCallback && this.animationCallback.call(null), this.nextFrame = requestAnimationFrame(p)) : p(), this.animationCallback = a;
          }
        }
      },
      {
        key: "animatedZoom",
        value: function(r) {
          return r ? typeof r == "number" ? this.animate({
            ratio: this.ratio / r
          }) : this.animate({
            ratio: this.ratio / (r.factor || ra)
          }, r) : this.animate({
            ratio: this.ratio / ra
          });
        }
      },
      {
        key: "animatedUnzoom",
        value: function(r) {
          return r ? typeof r == "number" ? this.animate({
            ratio: this.ratio * r
          }) : this.animate({
            ratio: this.ratio * (r.factor || ra)
          }, r) : this.animate({
            ratio: this.ratio * ra
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
  }(fc);
  function yn(e, t) {
    var n = t.getBoundingClientRect();
    return {
      x: e.clientX - n.left,
      y: e.clientY - n.top
    };
  }
  function Nn(e, t) {
    var n = ee(ee({}, yn(e, t)), {}, {
      sigmaDefaultPrevented: false,
      preventSigmaDefault: function() {
        n.sigmaDefaultPrevented = true;
      },
      original: e
    });
    return n;
  }
  function Gi(e) {
    var t = "x" in e ? e : ee(ee({}, e.touches[0] || e.previousTouches[0]), {}, {
      original: e.original,
      sigmaDefaultPrevented: e.sigmaDefaultPrevented,
      preventSigmaDefault: function() {
        e.sigmaDefaultPrevented = true, t.sigmaDefaultPrevented = true;
      }
    });
    return t;
  }
  function Yw(e, t) {
    return ee(ee({}, Nn(e, t)), {}, {
      delta: Eg(e)
    });
  }
  var Qw = 2;
  function _a(e) {
    for (var t = [], n = 0, r = Math.min(e.length, Qw); n < r; n++) t.push(e[n]);
    return t;
  }
  function Ui(e, t, n) {
    var r = {
      touches: _a(e.touches).map(function(i) {
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
  function Eg(e) {
    if (typeof e.deltaY < "u") return e.deltaY * -3 / 360;
    if (typeof e.detail < "u") return e.detail / -9;
    throw new Error("Captor: could not extract delta from event.");
  }
  var Sg = function(e) {
    function t(n, r) {
      var i;
      return xt(this, t), i = an(this, t), i.container = n, i.renderer = r, i;
    }
    return sn(t, e), Tt(t);
  }(fc), Xw = [
    "doubleClickTimeout",
    "doubleClickZoomingDuration",
    "doubleClickZoomingRatio",
    "dragTimeout",
    "draggedEventsTolerance",
    "inertiaDuration",
    "inertiaRatio",
    "zoomDuration",
    "zoomingRatio"
  ], Zw = Xw.reduce(function(e, t) {
    return ee(ee({}, e), {}, M({}, t, hc[t]));
  }, {}), qw = function(e) {
    function t(n, r) {
      var i;
      return xt(this, t), i = an(this, t, [
        n,
        r
      ]), M(i, "enabled", true), M(i, "draggedEvents", 0), M(i, "downStartTime", null), M(i, "lastMouseX", null), M(i, "lastMouseY", null), M(i, "isMouseDown", false), M(i, "isMoving", false), M(i, "movingTimeout", null), M(i, "startCameraState", null), M(i, "clicks", 0), M(i, "doubleClickTimeout", null), M(i, "currentWheelDirection", 0), M(i, "settings", Zw), i.handleClick = i.handleClick.bind(i), i.handleRightClick = i.handleRightClick.bind(i), i.handleDown = i.handleDown.bind(i), i.handleUp = i.handleUp.bind(i), i.handleMove = i.handleMove.bind(i), i.handleWheel = i.handleWheel.bind(i), i.handleLeave = i.handleLeave.bind(i), i.handleEnter = i.handleEnter.bind(i), n.addEventListener("click", i.handleClick, {
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
    return sn(t, e), Tt(t, [
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
            }, this.settings.doubleClickTimeout), this.draggedEvents < this.settings.draggedEventsTolerance && this.emit("click", Nn(r, this.container));
          }
        }
      },
      {
        key: "handleRightClick",
        value: function(r) {
          this.enabled && this.emit("rightClick", Nn(r, this.container));
        }
      },
      {
        key: "handleDoubleClick",
        value: function(r) {
          if (this.enabled) {
            r.preventDefault(), r.stopPropagation();
            var i = Nn(r, this.container);
            if (this.emit("doubleClick", i), !i.sigmaDefaultPrevented) {
              var o = this.renderer.getCamera(), a = o.getBoundedRatio(o.getState().ratio / this.settings.doubleClickZoomingRatio);
              o.animate(this.renderer.getViewportZoomedState(yn(r, this.container), a), {
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
              var i = yn(r, this.container), o = i.x, a = i.y;
              this.lastMouseX = o, this.lastMouseY = a, this.draggedEvents = 0, this.downStartTime = Date.now(), this.isMouseDown = true;
            }
            this.emit("mousedown", Nn(r, this.container));
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
            var a = yn(r, this.container), s = a.x, l = a.y, c = o.getState(), h = o.getPreviousState() || {
              x: 0,
              y: 0
            };
            this.isMoving ? o.animate({
              x: c.x + this.settings.inertiaRatio * (c.x - h.x),
              y: c.y + this.settings.inertiaRatio * (c.y - h.y)
            }, {
              duration: this.settings.inertiaDuration,
              easing: "quadraticOut"
            }) : (this.lastMouseX !== s || this.lastMouseY !== l) && o.setState({
              x: c.x,
              y: c.y
            }), this.isMoving = false, setTimeout(function() {
              var f = i.draggedEvents > 0;
              i.draggedEvents = 0, f && i.renderer.getSetting("hideEdgesOnMove") && i.renderer.refresh();
            }, 0), this.emit("mouseup", Nn(r, this.container));
          }
        }
      },
      {
        key: "handleMove",
        value: function(r) {
          var i = this;
          if (this.enabled) {
            var o = Nn(r, this.container);
            if (this.emit("mousemovebody", o), (r.target === this.container || r.composedPath()[0] === this.container) && this.emit("mousemove", o), !o.sigmaDefaultPrevented && this.isMouseDown) {
              this.isMoving = true, this.draggedEvents++, typeof this.movingTimeout == "number" && clearTimeout(this.movingTimeout), this.movingTimeout = window.setTimeout(function() {
                i.movingTimeout = null, i.isMoving = false;
              }, this.settings.dragTimeout);
              var a = this.renderer.getCamera(), s = yn(r, this.container), l = s.x, c = s.y, h = this.renderer.viewportToFramedGraph({
                x: this.lastMouseX,
                y: this.lastMouseY
              }), f = this.renderer.viewportToFramedGraph({
                x: l,
                y: c
              }), p = h.x - f.x, y = h.y - f.y, k = a.getState(), b = k.x + p, I = k.y + y;
              a.setState({
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
          this.emit("mouseleave", Nn(r, this.container));
        }
      },
      {
        key: "handleEnter",
        value: function(r) {
          this.emit("mouseenter", Nn(r, this.container));
        }
      },
      {
        key: "handleWheel",
        value: function(r) {
          var i = this, o = this.renderer.getCamera();
          if (!(!this.enabled || !o.enabledZooming)) {
            var a = Eg(r);
            if (a) {
              var s = Yw(r, this.container);
              if (this.emit("wheel", s), s.sigmaDefaultPrevented) {
                r.preventDefault(), r.stopPropagation();
                return;
              }
              var l = o.getState().ratio, c = a > 0 ? 1 / this.settings.zoomingRatio : this.settings.zoomingRatio, h = o.getBoundedRatio(l * c), f = a > 0 ? 1 : -1, p = Date.now();
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
  }(Sg), Jw = [
    "dragTimeout",
    "inertiaDuration",
    "inertiaRatio",
    "doubleClickTimeout",
    "doubleClickZoomingRatio",
    "doubleClickZoomingDuration",
    "tapMoveTolerance"
  ], eE = Jw.reduce(function(e, t) {
    return ee(ee({}, e), {}, M({}, t, hc[t]));
  }, {}), tE = function(e) {
    function t(n, r) {
      var i;
      return xt(this, t), i = an(this, t, [
        n,
        r
      ]), M(i, "enabled", true), M(i, "isMoving", false), M(i, "hasMoved", false), M(i, "touchMode", 0), M(i, "startTouchesPositions", []), M(i, "lastTouches", []), M(i, "lastTap", null), M(i, "settings", eE), i.handleStart = i.handleStart.bind(i), i.handleLeave = i.handleLeave.bind(i), i.handleMove = i.handleMove.bind(i), n.addEventListener("touchstart", i.handleStart, {
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
    return sn(t, e), Tt(t, [
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
            var o = _a(r.touches);
            if (this.touchMode = o.length, this.startCameraState = this.renderer.getCamera().getState(), this.startTouchesPositions = o.map(function(y) {
              return yn(y, i.container);
            }), this.touchMode === 2) {
              var a = mi(this.startTouchesPositions, 2), s = a[0], l = s.x, c = s.y, h = a[1], f = h.x, p = h.y;
              this.startTouchesAngle = Math.atan2(p - c, f - l), this.startTouchesDistance = Math.sqrt(Math.pow(f - l, 2) + Math.pow(p - c, 2));
            }
            this.emit("touchdown", Ui(r, this.lastTouches, this.container)), this.lastTouches = o, this.lastTouchesPositions = this.startTouchesPositions;
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
                  var i = this.renderer.getCamera(), o = i.getState(), a = i.getPreviousState() || {
                    x: 0,
                    y: 0
                  };
                  i.animate({
                    x: o.x + this.settings.inertiaRatio * (o.x - a.x),
                    y: o.y + this.settings.inertiaRatio * (o.y - a.y)
                  }, {
                    duration: this.settings.inertiaDuration,
                    easing: "quadraticOut"
                  });
                }
                this.hasMoved = false, this.isMoving = false, this.touchMode = 0;
                break;
            }
            if (this.emit("touchup", Ui(r, this.lastTouches, this.container)), !r.touches.length) {
              var s = yn(this.lastTouches[0], this.container), l = this.startTouchesPositions[0], c = Math.pow(s.x - l.x, 2) + Math.pow(s.y - l.y, 2);
              if (!r.touches.length && c < Math.pow(this.settings.tapMoveTolerance, 2)) if (this.lastTap && Date.now() - this.lastTap.time < this.settings.doubleClickTimeout) {
                var h = Ui(r, this.lastTouches, this.container);
                if (this.emit("doubletap", h), this.lastTap = null, !h.sigmaDefaultPrevented) {
                  var f = this.renderer.getCamera(), p = f.getBoundedRatio(f.getState().ratio / this.settings.doubleClickZoomingRatio);
                  f.animate(this.renderer.getViewportZoomedState(s, p), {
                    easing: "quadraticInOut",
                    duration: this.settings.doubleClickZoomingDuration
                  });
                }
              } else {
                var y = Ui(r, this.lastTouches, this.container);
                this.emit("tap", y), this.lastTap = {
                  time: Date.now(),
                  position: y.touches[0] || y.previousTouches[0]
                };
              }
            }
            this.lastTouches = _a(r.touches), this.startTouchesPositions = [];
          }
        }
      },
      {
        key: "handleMove",
        value: function(r) {
          var i = this;
          if (!(!this.enabled || !this.startTouchesPositions.length)) {
            r.preventDefault();
            var o = _a(r.touches), a = o.map(function(D) {
              return yn(D, i.container);
            }), s = this.lastTouches;
            this.lastTouches = o, this.lastTouchesPositions = a;
            var l = Ui(r, s, this.container);
            if (this.emit("touchmove", l), !l.sigmaDefaultPrevented && (this.hasMoved || (this.hasMoved = a.some(function(D, C) {
              var Y = i.startTouchesPositions[C];
              return Y && (D.x !== Y.x || D.y !== Y.y);
            })), !!this.hasMoved)) {
              this.isMoving = true, this.movingTimeout && clearTimeout(this.movingTimeout), this.movingTimeout = window.setTimeout(function() {
                i.isMoving = false;
              }, this.settings.dragTimeout);
              var c = this.renderer.getCamera(), h = this.startCameraState, f = this.renderer.getSetting("stagePadding");
              switch (this.touchMode) {
                case 1: {
                  var p = this.renderer.viewportToFramedGraph((this.startTouchesPositions || [])[0]), y = p.x, k = p.y, b = this.renderer.viewportToFramedGraph(a[0]), I = b.x, S = b.y;
                  c.setState({
                    x: h.x + y - I,
                    y: h.y + k - S
                  });
                  break;
                }
                case 2: {
                  var m = {
                    x: 0.5,
                    y: 0.5,
                    angle: 0,
                    ratio: 1
                  }, v = a[0], E = v.x, A = v.y, F = a[1], R = F.x, L = F.y, x = Math.atan2(L - A, R - E) - this.startTouchesAngle, G = Math.hypot(L - A, R - E) / this.startTouchesDistance, V = c.getBoundedRatio(h.ratio / G);
                  m.ratio = V, m.angle = h.angle + x;
                  var B = this.getDimensions(), W = this.renderer.viewportToFramedGraph((this.startTouchesPositions || [])[0], {
                    cameraState: h
                  }), O = Math.min(B.width, B.height) - 2 * f, re = O / B.width, fe = O / B.height, te = V / O, _ = E - O / 2 / re, $ = A - O / 2 / fe, H = [
                    _ * Math.cos(-m.angle) - $ * Math.sin(-m.angle),
                    $ * Math.cos(-m.angle) + _ * Math.sin(-m.angle)
                  ];
                  _ = H[0], $ = H[1], m.x = W.x - _ * te, m.y = W.y + $ * te, c.setState(m);
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
  }(Sg);
  function nE(e) {
    if (Array.isArray(e)) return cu(e);
  }
  function rE(e) {
    if (typeof Symbol < "u" && e[Symbol.iterator] != null || e["@@iterator"] != null) return Array.from(e);
  }
  function iE() {
    throw new TypeError(`Invalid attempt to spread non-iterable instance.
In order to be iterable, non-array objects must have a [Symbol.iterator]() method.`);
  }
  function of(e) {
    return nE(e) || rE(e) || Xp(e) || iE();
  }
  function oE(e, t) {
    if (e == null) return {};
    var n = {};
    for (var r in e) if ({}.hasOwnProperty.call(e, r)) {
      if (t.indexOf(r) !== -1) continue;
      n[r] = e[r];
    }
    return n;
  }
  function sl(e, t) {
    if (e == null) return {};
    var n, r, i = oE(e, t);
    if (Object.getOwnPropertySymbols) {
      var o = Object.getOwnPropertySymbols(e);
      for (r = 0; r < o.length; r++) n = o[r], t.indexOf(n) === -1 && {}.propertyIsEnumerable.call(e, n) && (i[n] = e[n]);
    }
    return i;
  }
  var af = function() {
    function e(t, n) {
      xt(this, e), this.key = t, this.size = n;
    }
    return Tt(e, null, [
      {
        key: "compare",
        value: function(n, r) {
          return n.size > r.size ? -1 : n.size < r.size || n.key > r.key ? 1 : -1;
        }
      }
    ]);
  }(), sf = function() {
    function e() {
      xt(this, e), M(this, "width", 0), M(this, "height", 0), M(this, "cellSize", 0), M(this, "columns", 0), M(this, "rows", 0), M(this, "cells", {});
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
          var o = new af(n, r), a = this.getIndex(i), s = this.cells[a];
          s || (s = [], this.cells[a] = s), s.push(o);
        }
      },
      {
        key: "organize",
        value: function() {
          for (var n in this.cells) {
            var r = this.cells[n];
            r.sort(af.compare);
          }
        }
      },
      {
        key: "getLabelsToDisplay",
        value: function(n, r) {
          var i = this.cellSize * this.cellSize, o = i / n / n, a = o * r / i, s = Math.ceil(a), l = [];
          for (var c in this.cells) for (var h = this.cells[c], f = 0; f < Math.min(s, h.length); f++) l.push(h[f].key);
          return l;
        }
      }
    ]);
  }();
  function aE(e) {
    var t = e.graph, n = e.hoveredNode, r = e.highlightedNodes, i = e.displayedNodeLabels, o = [];
    return t.forEachEdge(function(a, s, l, c) {
      (l === n || c === n || r.has(l) || r.has(c) || i.has(l) && i.has(c)) && o.push(a);
    }), o;
  }
  var lf = 150, uf = 50, Gn = Object.prototype.hasOwnProperty;
  function sE(e, t, n) {
    if (!Gn.call(n, "x") || !Gn.call(n, "y")) throw new Error('Sigma: could not find a valid position (x, y) for node "'.concat(t, '". All your nodes must have a number "x" and "y". Maybe your forgot to apply a layout or your "nodeReducer" is not returning the correct data?'));
    return n.color || (n.color = e.defaultNodeColor), !n.label && n.label !== "" && (n.label = null), n.label !== void 0 && n.label !== null ? n.label = "" + n.label : n.label = null, n.size || (n.size = 2), Gn.call(n, "hidden") || (n.hidden = false), Gn.call(n, "highlighted") || (n.highlighted = false), Gn.call(n, "forceLabel") || (n.forceLabel = false), (!n.type || n.type === "") && (n.type = e.defaultNodeType), n.zIndex || (n.zIndex = 0), n;
  }
  function lE(e, t, n) {
    return n.color || (n.color = e.defaultEdgeColor), n.label || (n.label = ""), n.size || (n.size = 0.5), Gn.call(n, "hidden") || (n.hidden = false), Gn.call(n, "forceLabel") || (n.forceLabel = false), (!n.type || n.type === "") && (n.type = e.defaultEdgeType), n.zIndex || (n.zIndex = 0), n;
  }
  var uE = function(e) {
    function t(n, r) {
      var i, o = arguments.length > 2 && arguments[2] !== void 0 ? arguments[2] : {};
      if (xt(this, t), i = an(this, t), M(i, "elements", {}), M(i, "canvasContexts", {}), M(i, "webGLContexts", {}), M(i, "pickingLayers", /* @__PURE__ */ new Set()), M(i, "textures", {}), M(i, "frameBuffers", {}), M(i, "activeListeners", {}), M(i, "labelGrid", new sf()), M(i, "nodeDataCache", {}), M(i, "edgeDataCache", {}), M(i, "nodeProgramIndex", {}), M(i, "edgeProgramIndex", {}), M(i, "nodesWithForcedLabels", /* @__PURE__ */ new Set()), M(i, "edgesWithForcedLabels", /* @__PURE__ */ new Set()), M(i, "nodeExtent", {
        x: [
          0,
          1
        ],
        y: [
          0,
          1
        ]
      }), M(i, "nodeZExtent", [
        1 / 0,
        -1 / 0
      ]), M(i, "edgeZExtent", [
        1 / 0,
        -1 / 0
      ]), M(i, "matrix", pn()), M(i, "invMatrix", pn()), M(i, "correctionRatio", 1), M(i, "customBBox", null), M(i, "normalizationFunction", tf({
        x: [
          0,
          1
        ],
        y: [
          0,
          1
        ]
      })), M(i, "graphToViewportRatio", 1), M(i, "itemIDsIndex", {}), M(i, "nodeIndices", {}), M(i, "edgeIndices", {}), M(i, "width", 0), M(i, "height", 0), M(i, "pixelRatio", Jd()), M(i, "pickingDownSizingRatio", 2 * i.pixelRatio), M(i, "displayedNodeLabels", /* @__PURE__ */ new Set()), M(i, "displayedEdgeLabels", /* @__PURE__ */ new Set()), M(i, "highlightedNodes", /* @__PURE__ */ new Set()), M(i, "hoveredNode", null), M(i, "hoveredEdge", null), M(i, "renderFrame", null), M(i, "renderHighlightedNodesFrame", null), M(i, "needToProcess", false), M(i, "checkEdgesEventsFrame", null), M(i, "nodePrograms", {}), M(i, "nodeHoverPrograms", {}), M(i, "edgePrograms", {}), i.settings = Kw(o), al(i.settings), jw(n), !(r instanceof HTMLElement)) throw new Error("Sigma: container should be an html element.");
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
      for (var a in i.settings.nodeProgramClasses) i.registerNodeProgram(a, i.settings.nodeProgramClasses[a], i.settings.nodeHoverProgramClasses[a]);
      for (var s in i.settings.edgeProgramClasses) i.registerEdgeProgram(s, i.settings.edgeProgramClasses[s]);
      return i.camera = new rf(), i.bindCameraHandlers(), i.mouseCaptor = new qw(i.elements.mouse, i), i.mouseCaptor.setSettings(i.settings), i.touchCaptor = new tE(i.elements.mouse, i), i.touchCaptor.setSettings(i.settings), i.bindEventHandlers(), i.bindGraphHandlers(), i.handleSettingsUpdate(), i.refresh(), i;
    }
    return sn(t, e), Tt(t, [
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
            var i = this.nodePrograms, o = i[r], a = sl(i, [
              r
            ].map(ao));
            o.kill(), this.nodePrograms = a;
          }
          if (this.nodeHoverPrograms[r]) {
            var s = this.nodeHoverPrograms, l = s[r], c = sl(s, [
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
            var i = this.edgePrograms, o = i[r], a = sl(i, [
              r
            ].map(ao));
            o.kill(), this.edgePrograms = a;
          }
          return this;
        }
      },
      {
        key: "resetWebGLTexture",
        value: function(r) {
          var i = this.webGLContexts[r], o = this.frameBuffers[r], a = this.textures[r];
          a && i.deleteTexture(a);
          var s = i.createTexture();
          return i.bindFramebuffer(i.FRAMEBUFFER, o), i.bindTexture(i.TEXTURE_2D, s), i.texImage2D(i.TEXTURE_2D, 0, i.RGBA, this.width, this.height, 0, i.RGBA, i.UNSIGNED_BYTE, null), i.framebufferTexture2D(i.FRAMEBUFFER, i.COLOR_ATTACHMENT0, i.TEXTURE_2D, s, 0), this.textures[r] = s, this;
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
          var i = r.x, o = r.y, a = Md(this.webGLContexts.nodes, this.frameBuffers.nodes, i, o, this.pixelRatio, this.pickingDownSizingRatio), s = Bd.apply(void 0, of(a)), l = this.itemIDsIndex[s];
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
            var a = Gi(o), s = {
              event: a,
              preventSigmaDefault: function() {
                a.preventSigmaDefault();
              }
            }, l = r.getNodeAtPosition(a);
            if (l && r.hoveredNode !== l && !r.nodeDataCache[l].hidden) {
              r.hoveredNode && r.emit("leaveNode", ee(ee({}, s), {}, {
                node: r.hoveredNode
              })), r.hoveredNode = l, r.emit("enterNode", ee(ee({}, s), {}, {
                node: l
              })), r.scheduleHighlightedNodesRender();
              return;
            }
            if (r.hoveredNode && r.getNodeAtPosition(a) !== r.hoveredNode) {
              var c = r.hoveredNode;
              r.hoveredNode = null, r.emit("leaveNode", ee(ee({}, s), {}, {
                node: c
              })), r.scheduleHighlightedNodesRender();
              return;
            }
            if (r.settings.enableEdgeEvents) {
              var h = r.hoveredNode ? null : r.getEdgeAtPoint(s.event.x, s.event.y);
              h !== r.hoveredEdge && (r.hoveredEdge && r.emit("leaveEdge", ee(ee({}, s), {}, {
                edge: r.hoveredEdge
              })), h && r.emit("enterEdge", ee(ee({}, s), {}, {
                edge: h
              })), r.hoveredEdge = h);
            }
          }, this.activeListeners.handleMoveBody = function(o) {
            var a = Gi(o);
            r.emit("moveBody", {
              event: a,
              preventSigmaDefault: function() {
                a.preventSigmaDefault();
              }
            });
          }, this.activeListeners.handleLeave = function(o) {
            var a = Gi(o), s = {
              event: a,
              preventSigmaDefault: function() {
                a.preventSigmaDefault();
              }
            };
            r.hoveredNode && (r.emit("leaveNode", ee(ee({}, s), {}, {
              node: r.hoveredNode
            })), r.scheduleHighlightedNodesRender()), r.settings.enableEdgeEvents && r.hoveredEdge && (r.emit("leaveEdge", ee(ee({}, s), {}, {
              edge: r.hoveredEdge
            })), r.scheduleHighlightedNodesRender()), r.emit("leaveStage", ee({}, s));
          }, this.activeListeners.handleEnter = function(o) {
            var a = Gi(o), s = {
              event: a,
              preventSigmaDefault: function() {
                a.preventSigmaDefault();
              }
            };
            r.emit("enterStage", ee({}, s));
          };
          var i = function(a) {
            return function(s) {
              var l = Gi(s), c = {
                event: l,
                preventSigmaDefault: function() {
                  l.preventSigmaDefault();
                }
              }, h = r.getNodeAtPosition(l);
              if (h) return r.emit("".concat(a, "Node"), ee(ee({}, c), {}, {
                node: h
              }));
              if (r.settings.enableEdgeEvents) {
                var f = r.getEdgeAtPoint(l.x, l.y);
                if (f) return r.emit("".concat(a, "Edge"), ee(ee({}, c), {}, {
                  edge: f
                }));
              }
              return r.emit("".concat(a, "Stage"), c);
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
          return this.activeListeners.eachNodeAttributesUpdatedGraphUpdate = function(a) {
            var s, l = (s = a.hints) === null || s === void 0 ? void 0 : s.attributes;
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
          }, this.activeListeners.eachEdgeAttributesUpdatedGraphUpdate = function(a) {
            var s, l = (s = a.hints) === null || s === void 0 ? void 0 : s.attributes;
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
          }, this.activeListeners.addNodeGraphUpdate = function(a) {
            var s = a.key;
            r.addNode(s), r.refresh({
              partialGraph: {
                nodes: [
                  s
                ]
              },
              skipIndexation: false,
              schedule: true
            });
          }, this.activeListeners.updateNodeGraphUpdate = function(a) {
            var s = a.key;
            r.refresh({
              partialGraph: {
                nodes: [
                  s
                ]
              },
              skipIndexation: false,
              schedule: true
            });
          }, this.activeListeners.dropNodeGraphUpdate = function(a) {
            var s = a.key;
            r.removeNode(s), r.refresh({
              schedule: true
            });
          }, this.activeListeners.addEdgeGraphUpdate = function(a) {
            var s = a.key;
            r.addEdge(s), r.refresh({
              partialGraph: {
                edges: [
                  s
                ]
              },
              schedule: true
            });
          }, this.activeListeners.updateEdgeGraphUpdate = function(a) {
            var s = a.key;
            r.refresh({
              partialGraph: {
                edges: [
                  s
                ]
              },
              skipIndexation: false,
              schedule: true
            });
          }, this.activeListeners.dropEdgeGraphUpdate = function(a) {
            var s = a.key;
            r.removeEdge(s), r.refresh({
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
          var o = Md(this.webGLContexts.edges, this.frameBuffers.edges, r, i, this.pixelRatio, this.pickingDownSizingRatio), a = Bd.apply(void 0, of(o)), s = this.itemIDsIndex[a];
          return s && s.type === "edge" ? s.id : null;
        }
      },
      {
        key: "process",
        value: function() {
          var r = this;
          this.emit("beforeProcess");
          var i = this.graph, o = this.settings, a = this.getDimensions();
          if (this.nodeExtent = $w(this.graph), !this.settings.autoRescale) {
            var s = a.width, l = a.height, c = this.nodeExtent, h = c.x, f = c.y;
            this.nodeExtent = {
              x: [
                (h[0] + h[1]) / 2 - s / 2,
                (h[0] + h[1]) / 2 + s / 2
              ],
              y: [
                (f[0] + f[1]) / 2 - l / 2,
                (f[0] + f[1]) / 2 + l / 2
              ]
            };
          }
          this.normalizationFunction = tf(this.customBBox || this.nodeExtent);
          var p = new rf(), y = Oi(p.getState(), a, this.getGraphDimensions(), this.getStagePadding());
          this.labelGrid.resizeAndClear(a, o.labelGridCellSize);
          for (var k = {}, b = {}, I = {}, S = {}, m = 1, v = i.nodes(), E = 0, A = v.length; E < A; E++) {
            var F = v[E], R = this.nodeDataCache[F], L = i.getNodeAttributes(F);
            R.x = L.x, R.y = L.y, this.normalizationFunction.applyTo(R), typeof R.label == "string" && !R.hidden && this.labelGrid.add(F, R.size, this.framedGraphToViewport(R, {
              matrix: y
            })), k[R.type] = (k[R.type] || 0) + 1;
          }
          this.labelGrid.organize();
          for (var x in this.nodePrograms) {
            if (!Gn.call(this.nodePrograms, x)) throw new Error('Sigma: could not find a suitable program for node type "'.concat(x, '"!'));
            this.nodePrograms[x].reallocate(k[x] || 0), k[x] = 0;
          }
          this.settings.zIndex && this.nodeZExtent[0] !== this.nodeZExtent[1] && (v = ef(this.nodeZExtent, function(_e) {
            return r.nodeDataCache[_e].zIndex;
          }, v));
          for (var G = 0, V = v.length; G < V; G++) {
            var B = v[G];
            b[B] = m, S[b[B]] = {
              type: "node",
              id: B
            }, m++;
            var W = this.nodeDataCache[B];
            this.addNodeToProgram(B, b[B], k[W.type]++);
          }
          for (var O = {}, re = i.edges(), fe = 0, te = re.length; fe < te; fe++) {
            var _ = re[fe], $ = this.edgeDataCache[_];
            O[$.type] = (O[$.type] || 0) + 1;
          }
          this.settings.zIndex && this.edgeZExtent[0] !== this.edgeZExtent[1] && (re = ef(this.edgeZExtent, function(_e) {
            return r.edgeDataCache[_e].zIndex;
          }, re));
          for (var H in this.edgePrograms) {
            if (!Gn.call(this.edgePrograms, H)) throw new Error('Sigma: could not find a suitable program for edge type "'.concat(H, '"!'));
            this.edgePrograms[H].reallocate(O[H] || 0), O[H] = 0;
          }
          for (var D = 0, C = re.length; D < C; D++) {
            var Y = re[D];
            I[Y] = m, S[I[Y]] = {
              type: "edge",
              id: Y
            }, m++;
            var ie = this.edgeDataCache[Y];
            this.addEdgeToProgram(Y, I[Y], O[ie.type]++);
          }
          return this.itemIDsIndex = S, this.nodeIndices = b, this.edgeIndices = I, this.emit("afterProcess"), this;
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
              for (var a in o.edgeProgramClasses) o.edgeProgramClasses[a] !== r.edgeProgramClasses[a] && this.registerEdgeProgram(a, o.edgeProgramClasses[a]);
              for (var s in r.edgeProgramClasses) o.edgeProgramClasses[s] || this.unregisterEdgeProgram(s);
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
          var i = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : {}, o = i.tolerance, a = o === void 0 ? 0 : o, s = i.boundaries, l = ee({}, r), c = s || this.nodeExtent, h = mi(c.x, 2), f = h[0], p = h[1], y = mi(c.y, 2), k = y[0], b = y[1], I = [
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
          ], S = 1 / 0, m = -1 / 0, v = 1 / 0, E = -1 / 0;
          I.forEach(function(O) {
            var re = O.x, fe = O.y;
            S = Math.min(S, re), m = Math.max(m, re), v = Math.min(v, fe), E = Math.max(E, fe);
          });
          var A = m - S, F = E - v, R = this.getDimensions(), L = R.width, x = R.height, G = 0, V = 0;
          if (A >= L ? m < L - a ? G = m - (L - a) : S > a && (G = S - a) : m > L + a ? G = m - (L + a) : S < -a && (G = S + a), F >= x ? E < x - a ? V = E - (x - a) : v > a && (V = v - a) : E > x + a ? V = E - (x + a) : v < -a && (V = v + a), G || V) {
            var B = this.viewportToFramedGraph({
              x: 0,
              y: 0
            }, {
              cameraState: r
            }), W = this.viewportToFramedGraph({
              x: G,
              y: V
            }, {
              cameraState: r
            });
            G = W.x - B.x, V = W.y - B.y, l.x += G, l.y += V;
          }
          return l;
        }
      },
      {
        key: "renderLabels",
        value: function() {
          if (!this.settings.renderLabels) return this;
          var r = this.camera.getState(), i = this.labelGrid.getLabelsToDisplay(r.ratio, this.settings.labelDensity);
          nf(i, this.nodesWithForcedLabels), this.displayedNodeLabels = /* @__PURE__ */ new Set();
          for (var o = this.canvasContexts.labels, a = 0, s = i.length; a < s; a++) {
            var l = i[a], c = this.nodeDataCache[l];
            if (!this.displayedNodeLabels.has(l) && !c.hidden) {
              var h = this.framedGraphToViewport(c), f = h.x, p = h.y, y = this.scaleSize(c.size);
              if (!(!c.forceLabel && y < this.settings.labelRenderedSizeThreshold) && !(f < -lf || f > this.width + lf || p < -uf || p > this.height + uf)) {
                this.displayedNodeLabels.add(l);
                var k = this.settings.defaultDrawNodeLabel, b = this.nodePrograms[c.type], I = (b == null ? void 0 : b.drawLabel) || k;
                I(o, ee(ee({
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
          var i = aE({
            graph: this.graph,
            hoveredNode: this.hoveredNode,
            displayedNodeLabels: this.displayedNodeLabels,
            highlightedNodes: this.highlightedNodes
          });
          nf(i, this.edgesWithForcedLabels);
          for (var o = /* @__PURE__ */ new Set(), a = 0, s = i.length; a < s; a++) {
            var l = i[a], c = this.graph.extremities(l), h = this.nodeDataCache[c[0]], f = this.nodeDataCache[c[1]], p = this.edgeDataCache[l];
            if (!o.has(l) && !(p.hidden || h.hidden || f.hidden)) {
              var y = this.settings.defaultDrawEdgeLabel, k = this.edgePrograms[p.type], b = (k == null ? void 0 : k.drawLabel) || y;
              b(r, ee(ee({
                key: l
              }, p), {}, {
                size: this.scaleSize(p.size)
              }), ee(ee(ee({
                key: c[0]
              }, h), this.framedGraphToViewport(h)), {}, {
                size: this.scaleSize(h.size)
              }), ee(ee(ee({
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
            var k = r.nodeDataCache[y], b = r.framedGraphToViewport(k), I = b.x, S = b.y, m = r.scaleSize(k.size), v = r.settings.defaultDrawNodeHover, E = r.nodePrograms[k.type], A = (E == null ? void 0 : E.drawHover) || v;
            A(i, ee(ee({
              key: y
            }, k), {}, {
              size: m,
              x: I,
              y: S
            }), r.settings);
          }, a = [];
          this.hoveredNode && !this.nodeDataCache[this.hoveredNode].hidden && a.push(this.hoveredNode), this.highlightedNodes.forEach(function(p) {
            p !== r.hoveredNode && a.push(p);
          }), a.forEach(function(p) {
            return o(p);
          });
          var s = {};
          a.forEach(function(p) {
            var y = r.nodeDataCache[p].type;
            s[y] = (s[y] || 0) + 1;
          });
          for (var l in this.nodeHoverPrograms) this.nodeHoverPrograms[l].reallocate(s[l] || 0), s[l] = 0;
          a.forEach(function(p) {
            var y = r.nodeDataCache[p];
            r.nodeHoverPrograms[y.type].process(0, s[y.type]++, y);
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
          var o = this.mouseCaptor, a = this.camera.isAnimated() || o.isMoving || o.draggedEvents || o.currentWheelDirection, s = this.camera.getState(), l = this.getDimensions(), c = this.getGraphDimensions(), h = this.getStagePadding();
          this.matrix = Oi(s, l, c, h), this.invMatrix = Oi(s, l, c, h, true), this.correctionRatio = Mw(this.matrix, s, l), this.graphToViewportRatio = this.getGraphToViewportRatio();
          var f = this.getRenderParams();
          for (var p in this.nodePrograms) {
            var y = this.nodePrograms[p];
            y.render(f);
          }
          if (!this.settings.hideEdgesOnMove || !a) for (var k in this.edgePrograms) {
            var b = this.edgePrograms[k];
            b.render(f);
          }
          return this.settings.hideLabelsOnMove && a || (this.renderLabels(), this.renderEdgeLabels(), this.renderHighlightedNodes()), i();
        }
      },
      {
        key: "addNode",
        value: function(r) {
          var i = Object.assign({}, this.graph.getNodeAttributes(r));
          this.settings.nodeReducer && (i = this.settings.nodeReducer(r, i));
          var o = sE(this.settings, r, i);
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
          var o = lE(this.settings, r, i);
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
          this.labelGrid = new sf(), this.nodeExtent = {
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
          var a = this.nodeDataCache[r], s = this.nodePrograms[a.type];
          if (!s) throw new Error('Sigma: could not find a suitable program for node type "'.concat(a.type, '"!'));
          s.process(i, o, a), this.nodeProgramIndex[r] = o;
        }
      },
      {
        key: "addEdgeToProgram",
        value: function(r, i, o) {
          var a = this.edgeDataCache[r], s = this.edgePrograms[a.type];
          if (!s) throw new Error('Sigma: could not find a suitable program for edge type "'.concat(a.type, '"!'));
          var l = this.graph.extremities(r), c = this.nodeDataCache[l[0]], h = this.nodeDataCache[l[1]];
          s.process(i, o, c, h, a), this.edgeProgramIndex[r] = o;
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
          var a = Hw(i, {
            position: "absolute"
          }, {
            class: "sigma-".concat(r)
          });
          return o.style && Object.assign(a.style, o.style), this.elements[r] = a, "beforeLayer" in o && o.beforeLayer ? this.elements[o.beforeLayer].before(a) : "afterLayer" in o && o.afterLayer ? this.elements[o.afterLayer].after(a) : this.container.appendChild(a), a;
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
          var i = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : {}, o = this.createCanvas(r, i), a = {
            preserveDrawingBuffer: false,
            antialias: false
          };
          return this.canvasContexts[r] = o.getContext("2d", a), this;
        }
      },
      {
        key: "createWebGLContext",
        value: function(r) {
          var i = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : {}, o = (i == null ? void 0 : i.canvas) || this.createCanvas(r, i);
          i.hidden && o.remove();
          var a = ee({
            preserveDrawingBuffer: false,
            antialias: false
          }, i), s;
          s = o.getContext("webgl2", a), s || (s = o.getContext("webgl", a)), s || (s = o.getContext("experimental-webgl", a));
          var l = s;
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
            var o, a = this.webGLContexts[r];
            (o = a.getExtension("WEBGL_lose_context")) === null || o === void 0 || o.loseContext(), delete this.webGLContexts[r];
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
          return ee({}, this.settings);
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
          var o = ee({}, this.settings);
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
          var i = ee({}, this.settings);
          return this.settings = ee(ee({}, this.settings), r), al(this.settings), this.handleSettingsUpdate(i), this.scheduleRefresh(), this;
        }
      },
      {
        key: "resize",
        value: function(r) {
          var i = this.width, o = this.height;
          if (this.width = this.container.offsetWidth, this.height = this.container.offsetHeight, this.pixelRatio = Jd(), this.width === 0) if (this.settings.allowInvalidContainer) this.width = 1;
          else throw new Error("Sigma: Container has no width. You can set the allowInvalidContainer setting to true to stop seeing this error.");
          if (this.height === 0) if (this.settings.allowInvalidContainer) this.height = 1;
          else throw new Error("Sigma: Container has no height. You can set the allowInvalidContainer setting to true to stop seeing this error.");
          if (!r && i === this.width && o === this.height) return this;
          for (var a in this.elements) {
            var s = this.elements[a];
            s.style.width = this.width + "px", s.style.height = this.height + "px";
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
          var i = this, o = (r == null ? void 0 : r.skipIndexation) !== void 0 ? r == null ? void 0 : r.skipIndexation : false, a = (r == null ? void 0 : r.schedule) !== void 0 ? r.schedule : false, s = !r || !r.partialGraph;
          if (s) this.clearEdgeIndices(), this.clearNodeIndices(), this.graph.forEachNode(function(E) {
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
            for (var b = (r == null || (c = r.partialGraph) === null || c === void 0 ? void 0 : c.edges) || [], I = 0, S = b.length; I < S; I++) {
              var m = b[I];
              if (this.updateEdge(m), o) {
                var v = this.edgeProgramIndex[m];
                if (v === void 0) throw new Error('Sigma: edge "'.concat(m, `" can't be repaint`));
                this.addEdgeToProgram(m, this.edgeIndices[m], v);
              }
            }
          }
          return (s || !o) && (this.needToProcess = true), a ? this.scheduleRender() : this.render(), this;
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
          return this.refresh(ee(ee({}, r), {}, {
            schedule: true
          }));
        }
      },
      {
        key: "getViewportZoomedState",
        value: function(r, i) {
          var o = this.camera.getState(), a = o.ratio, s = o.angle, l = o.x, c = o.y, h = this.settings, f = h.minCameraRatio, p = h.maxCameraRatio;
          typeof p == "number" && (i = Math.min(i, p)), typeof f == "number" && (i = Math.max(i, f));
          var y = i / a, k = {
            x: this.width / 2,
            y: this.height / 2
          }, b = this.viewportToFramedGraph(r), I = this.viewportToFramedGraph(k);
          return {
            angle: s,
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
          var i = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : {}, o = !!i.cameraState || !!i.viewportDimensions || !!i.graphDimensions, a = i.matrix ? i.matrix : o ? Oi(i.cameraState || this.camera.getState(), i.viewportDimensions || this.getDimensions(), i.graphDimensions || this.getGraphDimensions(), i.padding || this.getStagePadding()) : this.matrix, s = fu(a, r);
          return {
            x: (1 + s.x) * this.width / 2,
            y: (1 - s.y) * this.height / 2
          };
        }
      },
      {
        key: "viewportToFramedGraph",
        value: function(r) {
          var i = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : {}, o = !!i.cameraState || !!i.viewportDimensions || !i.graphDimensions, a = i.matrix ? i.matrix : o ? Oi(i.cameraState || this.camera.getState(), i.viewportDimensions || this.getDimensions(), i.graphDimensions || this.getGraphDimensions(), i.padding || this.getStagePadding(), true) : this.invMatrix, s = fu(a, {
            x: r.x / this.width * 2 - 1,
            y: 1 - r.y / this.height * 2
          });
          return isNaN(s.x) && (s.x = 0), isNaN(s.y) && (s.y = 0), s;
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
          }, o = Math.sqrt(Math.pow(r.x - i.x, 2) + Math.pow(r.y - i.y, 2)), a = this.graphToViewport(r), s = this.graphToViewport(i), l = Math.sqrt(Math.pow(a.x - s.x, 2) + Math.pow(a.y - s.y, 2));
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
          for (var a in this.edgePrograms) this.edgePrograms[a].kill();
          this.nodePrograms = {}, this.nodeHoverPrograms = {}, this.edgePrograms = {};
          for (var s in this.elements) this.killLayer(s);
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
  }(fc), cE = uE;
  function dE() {
    const e = arguments[0];
    for (let t = 1, n = arguments.length; t < n; t++) if (arguments[t]) for (const r in arguments[t]) e[r] = arguments[t][r];
    return e;
  }
  let it = dE;
  typeof Object.assign == "function" && (it = Object.assign);
  function nn(e, t, n, r) {
    const i = e._nodes.get(t);
    let o = null;
    return i && (r === "mixed" ? o = i.out && i.out[n] || i.undirected && i.undirected[n] : r === "directed" ? o = i.out && i.out[n] : o = i.undirected && i.undirected[n]), o;
  }
  function ht(e) {
    return typeof e == "object" && e !== null;
  }
  function _g(e) {
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
  function cf(e) {
    return !(!ht(e) || e.attributes && !Array.isArray(e.attributes));
  }
  function fE() {
    let e = Math.floor(Math.random() * 256) & 255;
    return () => e++;
  }
  function $n() {
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
  function _i() {
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
  class pc extends Error {
    constructor(t) {
      super(), this.name = "GraphError", this.message = t;
    }
  }
  class Q extends pc {
    constructor(t) {
      super(t), this.name = "InvalidArgumentsGraphError", typeof Error.captureStackTrace == "function" && Error.captureStackTrace(this, Q.prototype.constructor);
    }
  }
  class K extends pc {
    constructor(t) {
      super(t), this.name = "NotFoundGraphError", typeof Error.captureStackTrace == "function" && Error.captureStackTrace(this, K.prototype.constructor);
    }
  }
  class ue extends pc {
    constructor(t) {
      super(t), this.name = "UsageGraphError", typeof Error.captureStackTrace == "function" && Error.captureStackTrace(this, ue.prototype.constructor);
    }
  }
  function kg(e, t) {
    this.key = e, this.attributes = t, this.clear();
  }
  kg.prototype.clear = function() {
    this.inDegree = 0, this.outDegree = 0, this.undirectedDegree = 0, this.undirectedLoops = 0, this.directedLoops = 0, this.in = {}, this.out = {}, this.undirected = {};
  };
  function bg(e, t) {
    this.key = e, this.attributes = t, this.clear();
  }
  bg.prototype.clear = function() {
    this.inDegree = 0, this.outDegree = 0, this.directedLoops = 0, this.in = {}, this.out = {};
  };
  function Cg(e, t) {
    this.key = e, this.attributes = t, this.clear();
  }
  Cg.prototype.clear = function() {
    this.undirectedDegree = 0, this.undirectedLoops = 0, this.undirected = {};
  };
  function ki(e, t, n, r, i) {
    this.key = t, this.attributes = i, this.undirected = e, this.source = n, this.target = r;
  }
  ki.prototype.attach = function() {
    let e = "out", t = "in";
    this.undirected && (e = t = "undirected");
    const n = this.source.key, r = this.target.key;
    this.source[e][r] = this, !(this.undirected && n === r) && (this.target[t][n] = this);
  };
  ki.prototype.attachMulti = function() {
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
  ki.prototype.detach = function() {
    const e = this.source.key, t = this.target.key;
    let n = "out", r = "in";
    this.undirected && (n = r = "undirected"), delete this.source[n][t], delete this.target[r][e];
  };
  ki.prototype.detachMulti = function() {
    const e = this.source.key, t = this.target.key;
    let n = "out", r = "in";
    this.undirected && (n = r = "undirected"), this.previous === void 0 ? this.next === void 0 ? (delete this.source[n][t], delete this.target[r][e]) : (this.next.previous = void 0, this.source[n][t] = this.next, this.target[r][e] = this.next) : (this.previous.next = this.next, this.next !== void 0 && (this.next.previous = this.previous));
  };
  const xg = 0, Tg = 1, hE = 2, Rg = 3;
  function Yn(e, t, n, r, i, o, a) {
    let s, l, c, h;
    if (r = "" + r, n === xg) {
      if (s = e._nodes.get(r), !s) throw new K(`Graph.${t}: could not find the "${r}" node in the graph.`);
      c = i, h = o;
    } else if (n === Rg) {
      if (i = "" + i, l = e._edges.get(i), !l) throw new K(`Graph.${t}: could not find the "${i}" edge in the graph.`);
      const f = l.source.key, p = l.target.key;
      if (r === f) s = l.target;
      else if (r === p) s = l.source;
      else throw new K(`Graph.${t}: the "${r}" node is not attached to the "${i}" edge (${f}, ${p}).`);
      c = o, h = a;
    } else {
      if (l = e._edges.get(r), !l) throw new K(`Graph.${t}: could not find the "${r}" edge in the graph.`);
      n === Tg ? s = l.source : s = l.target, c = i, h = o;
    }
    return [
      s,
      c,
      h
    ];
  }
  function pE(e, t, n) {
    e.prototype[t] = function(r, i, o) {
      const [a, s] = Yn(this, t, n, r, i, o);
      return a.attributes[s];
    };
  }
  function gE(e, t, n) {
    e.prototype[t] = function(r, i) {
      const [o] = Yn(this, t, n, r, i);
      return o.attributes;
    };
  }
  function mE(e, t, n) {
    e.prototype[t] = function(r, i, o) {
      const [a, s] = Yn(this, t, n, r, i, o);
      return a.attributes.hasOwnProperty(s);
    };
  }
  function vE(e, t, n) {
    e.prototype[t] = function(r, i, o, a) {
      const [s, l, c] = Yn(this, t, n, r, i, o, a);
      return s.attributes[l] = c, this.emit("nodeAttributesUpdated", {
        key: s.key,
        type: "set",
        attributes: s.attributes,
        name: l
      }), this;
    };
  }
  function yE(e, t, n) {
    e.prototype[t] = function(r, i, o, a) {
      const [s, l, c] = Yn(this, t, n, r, i, o, a);
      if (typeof c != "function") throw new Q(`Graph.${t}: updater should be a function.`);
      const h = s.attributes, f = c(h[l]);
      return h[l] = f, this.emit("nodeAttributesUpdated", {
        key: s.key,
        type: "set",
        attributes: s.attributes,
        name: l
      }), this;
    };
  }
  function wE(e, t, n) {
    e.prototype[t] = function(r, i, o) {
      const [a, s] = Yn(this, t, n, r, i, o);
      return delete a.attributes[s], this.emit("nodeAttributesUpdated", {
        key: a.key,
        type: "remove",
        attributes: a.attributes,
        name: s
      }), this;
    };
  }
  function EE(e, t, n) {
    e.prototype[t] = function(r, i, o) {
      const [a, s] = Yn(this, t, n, r, i, o);
      if (!ht(s)) throw new Q(`Graph.${t}: provided attributes are not a plain object.`);
      return a.attributes = s, this.emit("nodeAttributesUpdated", {
        key: a.key,
        type: "replace",
        attributes: a.attributes
      }), this;
    };
  }
  function SE(e, t, n) {
    e.prototype[t] = function(r, i, o) {
      const [a, s] = Yn(this, t, n, r, i, o);
      if (!ht(s)) throw new Q(`Graph.${t}: provided attributes are not a plain object.`);
      return it(a.attributes, s), this.emit("nodeAttributesUpdated", {
        key: a.key,
        type: "merge",
        attributes: a.attributes,
        data: s
      }), this;
    };
  }
  function _E(e, t, n) {
    e.prototype[t] = function(r, i, o) {
      const [a, s] = Yn(this, t, n, r, i, o);
      if (typeof s != "function") throw new Q(`Graph.${t}: provided updater is not a function.`);
      return a.attributes = s(a.attributes), this.emit("nodeAttributesUpdated", {
        key: a.key,
        type: "update",
        attributes: a.attributes
      }), this;
    };
  }
  const kE = [
    {
      name: (e) => `get${e}Attribute`,
      attacher: pE
    },
    {
      name: (e) => `get${e}Attributes`,
      attacher: gE
    },
    {
      name: (e) => `has${e}Attribute`,
      attacher: mE
    },
    {
      name: (e) => `set${e}Attribute`,
      attacher: vE
    },
    {
      name: (e) => `update${e}Attribute`,
      attacher: yE
    },
    {
      name: (e) => `remove${e}Attribute`,
      attacher: wE
    },
    {
      name: (e) => `replace${e}Attributes`,
      attacher: EE
    },
    {
      name: (e) => `merge${e}Attributes`,
      attacher: SE
    },
    {
      name: (e) => `update${e}Attributes`,
      attacher: _E
    }
  ];
  function bE(e) {
    kE.forEach(function({ name: t, attacher: n }) {
      n(e, t("Node"), xg), n(e, t("Source"), Tg), n(e, t("Target"), hE), n(e, t("Opposite"), Rg);
    });
  }
  function CE(e, t, n) {
    e.prototype[t] = function(r, i) {
      let o;
      if (this.type !== "mixed" && n !== "mixed" && n !== this.type) throw new ue(`Graph.${t}: cannot find this type of edges in your ${this.type} graph.`);
      if (arguments.length > 2) {
        if (this.multi) throw new ue(`Graph.${t}: cannot use a {source,target} combo when asking about an edge's attributes in a MultiGraph since we cannot infer the one you want information about.`);
        const a = "" + r, s = "" + i;
        if (i = arguments[2], o = nn(this, a, s, n), !o) throw new K(`Graph.${t}: could not find an edge for the given path ("${a}" - "${s}").`);
      } else {
        if (n !== "mixed") throw new ue(`Graph.${t}: calling this method with only a key (vs. a source and target) does not make sense since an edge with this key could have the other type.`);
        if (r = "" + r, o = this._edges.get(r), !o) throw new K(`Graph.${t}: could not find the "${r}" edge in the graph.`);
      }
      return o.attributes[i];
    };
  }
  function xE(e, t, n) {
    e.prototype[t] = function(r) {
      let i;
      if (this.type !== "mixed" && n !== "mixed" && n !== this.type) throw new ue(`Graph.${t}: cannot find this type of edges in your ${this.type} graph.`);
      if (arguments.length > 1) {
        if (this.multi) throw new ue(`Graph.${t}: cannot use a {source,target} combo when asking about an edge's attributes in a MultiGraph since we cannot infer the one you want information about.`);
        const o = "" + r, a = "" + arguments[1];
        if (i = nn(this, o, a, n), !i) throw new K(`Graph.${t}: could not find an edge for the given path ("${o}" - "${a}").`);
      } else {
        if (n !== "mixed") throw new ue(`Graph.${t}: calling this method with only a key (vs. a source and target) does not make sense since an edge with this key could have the other type.`);
        if (r = "" + r, i = this._edges.get(r), !i) throw new K(`Graph.${t}: could not find the "${r}" edge in the graph.`);
      }
      return i.attributes;
    };
  }
  function TE(e, t, n) {
    e.prototype[t] = function(r, i) {
      let o;
      if (this.type !== "mixed" && n !== "mixed" && n !== this.type) throw new ue(`Graph.${t}: cannot find this type of edges in your ${this.type} graph.`);
      if (arguments.length > 2) {
        if (this.multi) throw new ue(`Graph.${t}: cannot use a {source,target} combo when asking about an edge's attributes in a MultiGraph since we cannot infer the one you want information about.`);
        const a = "" + r, s = "" + i;
        if (i = arguments[2], o = nn(this, a, s, n), !o) throw new K(`Graph.${t}: could not find an edge for the given path ("${a}" - "${s}").`);
      } else {
        if (n !== "mixed") throw new ue(`Graph.${t}: calling this method with only a key (vs. a source and target) does not make sense since an edge with this key could have the other type.`);
        if (r = "" + r, o = this._edges.get(r), !o) throw new K(`Graph.${t}: could not find the "${r}" edge in the graph.`);
      }
      return o.attributes.hasOwnProperty(i);
    };
  }
  function RE(e, t, n) {
    e.prototype[t] = function(r, i, o) {
      let a;
      if (this.type !== "mixed" && n !== "mixed" && n !== this.type) throw new ue(`Graph.${t}: cannot find this type of edges in your ${this.type} graph.`);
      if (arguments.length > 3) {
        if (this.multi) throw new ue(`Graph.${t}: cannot use a {source,target} combo when asking about an edge's attributes in a MultiGraph since we cannot infer the one you want information about.`);
        const s = "" + r, l = "" + i;
        if (i = arguments[2], o = arguments[3], a = nn(this, s, l, n), !a) throw new K(`Graph.${t}: could not find an edge for the given path ("${s}" - "${l}").`);
      } else {
        if (n !== "mixed") throw new ue(`Graph.${t}: calling this method with only a key (vs. a source and target) does not make sense since an edge with this key could have the other type.`);
        if (r = "" + r, a = this._edges.get(r), !a) throw new K(`Graph.${t}: could not find the "${r}" edge in the graph.`);
      }
      return a.attributes[i] = o, this.emit("edgeAttributesUpdated", {
        key: a.key,
        type: "set",
        attributes: a.attributes,
        name: i
      }), this;
    };
  }
  function AE(e, t, n) {
    e.prototype[t] = function(r, i, o) {
      let a;
      if (this.type !== "mixed" && n !== "mixed" && n !== this.type) throw new ue(`Graph.${t}: cannot find this type of edges in your ${this.type} graph.`);
      if (arguments.length > 3) {
        if (this.multi) throw new ue(`Graph.${t}: cannot use a {source,target} combo when asking about an edge's attributes in a MultiGraph since we cannot infer the one you want information about.`);
        const s = "" + r, l = "" + i;
        if (i = arguments[2], o = arguments[3], a = nn(this, s, l, n), !a) throw new K(`Graph.${t}: could not find an edge for the given path ("${s}" - "${l}").`);
      } else {
        if (n !== "mixed") throw new ue(`Graph.${t}: calling this method with only a key (vs. a source and target) does not make sense since an edge with this key could have the other type.`);
        if (r = "" + r, a = this._edges.get(r), !a) throw new K(`Graph.${t}: could not find the "${r}" edge in the graph.`);
      }
      if (typeof o != "function") throw new Q(`Graph.${t}: updater should be a function.`);
      return a.attributes[i] = o(a.attributes[i]), this.emit("edgeAttributesUpdated", {
        key: a.key,
        type: "set",
        attributes: a.attributes,
        name: i
      }), this;
    };
  }
  function LE(e, t, n) {
    e.prototype[t] = function(r, i) {
      let o;
      if (this.type !== "mixed" && n !== "mixed" && n !== this.type) throw new ue(`Graph.${t}: cannot find this type of edges in your ${this.type} graph.`);
      if (arguments.length > 2) {
        if (this.multi) throw new ue(`Graph.${t}: cannot use a {source,target} combo when asking about an edge's attributes in a MultiGraph since we cannot infer the one you want information about.`);
        const a = "" + r, s = "" + i;
        if (i = arguments[2], o = nn(this, a, s, n), !o) throw new K(`Graph.${t}: could not find an edge for the given path ("${a}" - "${s}").`);
      } else {
        if (n !== "mixed") throw new ue(`Graph.${t}: calling this method with only a key (vs. a source and target) does not make sense since an edge with this key could have the other type.`);
        if (r = "" + r, o = this._edges.get(r), !o) throw new K(`Graph.${t}: could not find the "${r}" edge in the graph.`);
      }
      return delete o.attributes[i], this.emit("edgeAttributesUpdated", {
        key: o.key,
        type: "remove",
        attributes: o.attributes,
        name: i
      }), this;
    };
  }
  function DE(e, t, n) {
    e.prototype[t] = function(r, i) {
      let o;
      if (this.type !== "mixed" && n !== "mixed" && n !== this.type) throw new ue(`Graph.${t}: cannot find this type of edges in your ${this.type} graph.`);
      if (arguments.length > 2) {
        if (this.multi) throw new ue(`Graph.${t}: cannot use a {source,target} combo when asking about an edge's attributes in a MultiGraph since we cannot infer the one you want information about.`);
        const a = "" + r, s = "" + i;
        if (i = arguments[2], o = nn(this, a, s, n), !o) throw new K(`Graph.${t}: could not find an edge for the given path ("${a}" - "${s}").`);
      } else {
        if (n !== "mixed") throw new ue(`Graph.${t}: calling this method with only a key (vs. a source and target) does not make sense since an edge with this key could have the other type.`);
        if (r = "" + r, o = this._edges.get(r), !o) throw new K(`Graph.${t}: could not find the "${r}" edge in the graph.`);
      }
      if (!ht(i)) throw new Q(`Graph.${t}: provided attributes are not a plain object.`);
      return o.attributes = i, this.emit("edgeAttributesUpdated", {
        key: o.key,
        type: "replace",
        attributes: o.attributes
      }), this;
    };
  }
  function PE(e, t, n) {
    e.prototype[t] = function(r, i) {
      let o;
      if (this.type !== "mixed" && n !== "mixed" && n !== this.type) throw new ue(`Graph.${t}: cannot find this type of edges in your ${this.type} graph.`);
      if (arguments.length > 2) {
        if (this.multi) throw new ue(`Graph.${t}: cannot use a {source,target} combo when asking about an edge's attributes in a MultiGraph since we cannot infer the one you want information about.`);
        const a = "" + r, s = "" + i;
        if (i = arguments[2], o = nn(this, a, s, n), !o) throw new K(`Graph.${t}: could not find an edge for the given path ("${a}" - "${s}").`);
      } else {
        if (n !== "mixed") throw new ue(`Graph.${t}: calling this method with only a key (vs. a source and target) does not make sense since an edge with this key could have the other type.`);
        if (r = "" + r, o = this._edges.get(r), !o) throw new K(`Graph.${t}: could not find the "${r}" edge in the graph.`);
      }
      if (!ht(i)) throw new Q(`Graph.${t}: provided attributes are not a plain object.`);
      return it(o.attributes, i), this.emit("edgeAttributesUpdated", {
        key: o.key,
        type: "merge",
        attributes: o.attributes,
        data: i
      }), this;
    };
  }
  function IE(e, t, n) {
    e.prototype[t] = function(r, i) {
      let o;
      if (this.type !== "mixed" && n !== "mixed" && n !== this.type) throw new ue(`Graph.${t}: cannot find this type of edges in your ${this.type} graph.`);
      if (arguments.length > 2) {
        if (this.multi) throw new ue(`Graph.${t}: cannot use a {source,target} combo when asking about an edge's attributes in a MultiGraph since we cannot infer the one you want information about.`);
        const a = "" + r, s = "" + i;
        if (i = arguments[2], o = nn(this, a, s, n), !o) throw new K(`Graph.${t}: could not find an edge for the given path ("${a}" - "${s}").`);
      } else {
        if (n !== "mixed") throw new ue(`Graph.${t}: calling this method with only a key (vs. a source and target) does not make sense since an edge with this key could have the other type.`);
        if (r = "" + r, o = this._edges.get(r), !o) throw new K(`Graph.${t}: could not find the "${r}" edge in the graph.`);
      }
      if (typeof i != "function") throw new Q(`Graph.${t}: provided updater is not a function.`);
      return o.attributes = i(o.attributes), this.emit("edgeAttributesUpdated", {
        key: o.key,
        type: "update",
        attributes: o.attributes
      }), this;
    };
  }
  const FE = [
    {
      name: (e) => `get${e}Attribute`,
      attacher: CE
    },
    {
      name: (e) => `get${e}Attributes`,
      attacher: xE
    },
    {
      name: (e) => `has${e}Attribute`,
      attacher: TE
    },
    {
      name: (e) => `set${e}Attribute`,
      attacher: RE
    },
    {
      name: (e) => `update${e}Attribute`,
      attacher: AE
    },
    {
      name: (e) => `remove${e}Attribute`,
      attacher: LE
    },
    {
      name: (e) => `replace${e}Attributes`,
      attacher: DE
    },
    {
      name: (e) => `merge${e}Attributes`,
      attacher: PE
    },
    {
      name: (e) => `update${e}Attributes`,
      attacher: IE
    }
  ];
  function NE(e) {
    FE.forEach(function({ name: t, attacher: n }) {
      n(e, t("Edge"), "mixed"), n(e, t("DirectedEdge"), "directed"), n(e, t("UndirectedEdge"), "undirected");
    });
  }
  const zE = [
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
  function OE(e, t, n, r) {
    let i = false;
    for (const o in t) {
      if (o === r) continue;
      const a = t[o];
      if (i = n(a.key, a.attributes, a.source.key, a.target.key, a.source.attributes, a.target.attributes, a.undirected), e && i) return a.key;
    }
  }
  function GE(e, t, n, r) {
    let i, o, a, s = false;
    for (const l in t) if (l !== r) {
      i = t[l];
      do {
        if (o = i.source, a = i.target, s = n(i.key, i.attributes, o.key, a.key, o.attributes, a.attributes, i.undirected), e && s) return i.key;
        i = i.next;
      } while (i !== void 0);
    }
  }
  function ll(e, t) {
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
            const a = n[o++];
            if (a === t) {
              i = void 0;
              continue;
            }
            i = e[a];
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
  function UE(e, t, n, r) {
    const i = t[n];
    if (!i) return;
    const o = i.source, a = i.target;
    if (r(i.key, i.attributes, o.key, a.key, o.attributes, a.attributes, i.undirected) && e) return i.key;
  }
  function BE(e, t, n, r) {
    let i = t[n];
    if (!i) return;
    let o = false;
    do {
      if (o = r(i.key, i.attributes, i.source.key, i.target.key, i.source.attributes, i.target.attributes, i.undirected), e && o) return i.key;
      i = i.next;
    } while (i !== void 0);
  }
  function ul(e, t) {
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
  function ME(e, t) {
    if (e.size === 0) return [];
    if (t === "mixed" || t === e.type) return Array.from(e._edges.keys());
    const n = t === "undirected" ? e.undirectedSize : e.directedSize, r = new Array(n), i = t === "undirected", o = e._edges.values();
    let a = 0, s, l;
    for (; s = o.next(), s.done !== true; ) l = s.value, l.undirected === i && (r[a++] = l.key);
    return r;
  }
  function Ag(e, t, n, r) {
    if (t.size === 0) return;
    const i = n !== "mixed" && n !== t.type, o = n === "undirected";
    let a, s, l = false;
    const c = t._edges.values();
    for (; a = c.next(), a.done !== true; ) {
      if (s = a.value, i && s.undirected !== o) continue;
      const { key: h, attributes: f, source: p, target: y } = s;
      if (l = r(h, f, p.key, y.key, p.attributes, y.attributes, s.undirected), e && l) return h;
    }
  }
  function $E(e, t) {
    if (e.size === 0) return _i();
    const n = t !== "mixed" && t !== e.type, r = t === "undirected", i = e._edges.values();
    return {
      [Symbol.iterator]() {
        return this;
      },
      next() {
        let o, a;
        for (; ; ) {
          if (o = i.next(), o.done) return o;
          if (a = o.value, !(n && a.undirected !== r)) break;
        }
        return {
          value: {
            edge: a.key,
            attributes: a.attributes,
            source: a.source.key,
            target: a.target.key,
            sourceAttributes: a.source.attributes,
            targetAttributes: a.target.attributes,
            undirected: a.undirected
          },
          done: false
        };
      }
    };
  }
  function gc(e, t, n, r, i, o) {
    const a = t ? GE : OE;
    let s;
    if (n !== "undirected" && (r !== "out" && (s = a(e, i.in, o), e && s) || r !== "in" && (s = a(e, i.out, o, r ? void 0 : i.key), e && s)) || n !== "directed" && (s = a(e, i.undirected, o), e && s)) return s;
  }
  function jE(e, t, n, r) {
    const i = [];
    return gc(false, e, t, n, r, function(o) {
      i.push(o);
    }), i;
  }
  function HE(e, t, n) {
    let r = _i();
    return e !== "undirected" && (t !== "out" && typeof n.in < "u" && (r = $n(r, ll(n.in))), t !== "in" && typeof n.out < "u" && (r = $n(r, ll(n.out, t ? void 0 : n.key)))), e !== "directed" && typeof n.undirected < "u" && (r = $n(r, ll(n.undirected))), r;
  }
  function mc(e, t, n, r, i, o, a) {
    const s = n ? BE : UE;
    let l;
    if (t !== "undirected" && (typeof i.in < "u" && r !== "out" && (l = s(e, i.in, o, a), e && l) || typeof i.out < "u" && r !== "in" && (r || i.key !== o) && (l = s(e, i.out, o, a), e && l)) || t !== "directed" && typeof i.undirected < "u" && (l = s(e, i.undirected, o, a), e && l)) return l;
  }
  function WE(e, t, n, r, i) {
    const o = [];
    return mc(false, e, t, n, r, i, function(a) {
      o.push(a);
    }), o;
  }
  function VE(e, t, n, r) {
    let i = _i();
    return e !== "undirected" && (typeof n.in < "u" && t !== "out" && r in n.in && (i = $n(i, ul(n.in, r))), typeof n.out < "u" && t !== "in" && r in n.out && (t || n.key !== r) && (i = $n(i, ul(n.out, r)))), e !== "directed" && typeof n.undirected < "u" && r in n.undirected && (i = $n(i, ul(n.undirected, r))), i;
  }
  function KE(e, t) {
    const { name: n, type: r, direction: i } = t;
    e.prototype[n] = function(o, a) {
      if (r !== "mixed" && this.type !== "mixed" && r !== this.type) return [];
      if (!arguments.length) return ME(this, r);
      if (arguments.length === 1) {
        o = "" + o;
        const s = this._nodes.get(o);
        if (typeof s > "u") throw new K(`Graph.${n}: could not find the "${o}" node in the graph.`);
        return jE(this.multi, r === "mixed" ? this.type : r, i, s);
      }
      if (arguments.length === 2) {
        o = "" + o, a = "" + a;
        const s = this._nodes.get(o);
        if (!s) throw new K(`Graph.${n}:  could not find the "${o}" source node in the graph.`);
        if (!this._nodes.has(a)) throw new K(`Graph.${n}:  could not find the "${a}" target node in the graph.`);
        return WE(r, this.multi, i, s, a);
      }
      throw new Q(`Graph.${n}: too many arguments (expecting 0, 1 or 2 and got ${arguments.length}).`);
    };
  }
  function YE(e, t) {
    const { name: n, type: r, direction: i } = t, o = "forEach" + n[0].toUpperCase() + n.slice(1, -1);
    e.prototype[o] = function(c, h, f) {
      if (!(r !== "mixed" && this.type !== "mixed" && r !== this.type)) {
        if (arguments.length === 1) return f = c, Ag(false, this, r, f);
        if (arguments.length === 2) {
          c = "" + c, f = h;
          const p = this._nodes.get(c);
          if (typeof p > "u") throw new K(`Graph.${o}: could not find the "${c}" node in the graph.`);
          return gc(false, this.multi, r === "mixed" ? this.type : r, i, p, f);
        }
        if (arguments.length === 3) {
          c = "" + c, h = "" + h;
          const p = this._nodes.get(c);
          if (!p) throw new K(`Graph.${o}:  could not find the "${c}" source node in the graph.`);
          if (!this._nodes.has(h)) throw new K(`Graph.${o}:  could not find the "${h}" target node in the graph.`);
          return mc(false, r, this.multi, i, p, h, f);
        }
        throw new Q(`Graph.${o}: too many arguments (expecting 1, 2 or 3 and got ${arguments.length}).`);
      }
    };
    const a = "map" + n[0].toUpperCase() + n.slice(1);
    e.prototype[a] = function() {
      const c = Array.prototype.slice.call(arguments), h = c.pop();
      let f;
      if (c.length === 0) {
        let p = 0;
        r !== "directed" && (p += this.undirectedSize), r !== "undirected" && (p += this.directedSize), f = new Array(p);
        let y = 0;
        c.push((k, b, I, S, m, v, E) => {
          f[y++] = h(k, b, I, S, m, v, E);
        });
      } else f = [], c.push((p, y, k, b, I, S, m) => {
        f.push(h(p, y, k, b, I, S, m));
      });
      return this[o].apply(this, c), f;
    };
    const s = "filter" + n[0].toUpperCase() + n.slice(1);
    e.prototype[s] = function() {
      const c = Array.prototype.slice.call(arguments), h = c.pop(), f = [];
      return c.push((p, y, k, b, I, S, m) => {
        h(p, y, k, b, I, S, m) && f.push(p);
      }), this[o].apply(this, c), f;
    };
    const l = "reduce" + n[0].toUpperCase() + n.slice(1);
    e.prototype[l] = function() {
      let c = Array.prototype.slice.call(arguments);
      if (c.length < 2 || c.length > 4) throw new Q(`Graph.${l}: invalid number of arguments (expecting 2, 3 or 4 and got ${c.length}).`);
      if (typeof c[c.length - 1] == "function" && typeof c[c.length - 2] != "function") throw new Q(`Graph.${l}: missing initial value. You must provide it because the callback takes more than one argument and we cannot infer the initial value from the first iteration, as you could with a simple array.`);
      let h, f;
      c.length === 2 ? (h = c[0], f = c[1], c = []) : c.length === 3 ? (h = c[1], f = c[2], c = [
        c[0]
      ]) : c.length === 4 && (h = c[2], f = c[3], c = [
        c[0],
        c[1]
      ]);
      let p = f;
      return c.push((y, k, b, I, S, m, v) => {
        p = h(p, y, k, b, I, S, m, v);
      }), this[o].apply(this, c), p;
    };
  }
  function QE(e, t) {
    const { name: n, type: r, direction: i } = t, o = "find" + n[0].toUpperCase() + n.slice(1, -1);
    e.prototype[o] = function(l, c, h) {
      if (r !== "mixed" && this.type !== "mixed" && r !== this.type) return false;
      if (arguments.length === 1) return h = l, Ag(true, this, r, h);
      if (arguments.length === 2) {
        l = "" + l, h = c;
        const f = this._nodes.get(l);
        if (typeof f > "u") throw new K(`Graph.${o}: could not find the "${l}" node in the graph.`);
        return gc(true, this.multi, r === "mixed" ? this.type : r, i, f, h);
      }
      if (arguments.length === 3) {
        l = "" + l, c = "" + c;
        const f = this._nodes.get(l);
        if (!f) throw new K(`Graph.${o}:  could not find the "${l}" source node in the graph.`);
        if (!this._nodes.has(c)) throw new K(`Graph.${o}:  could not find the "${c}" target node in the graph.`);
        return mc(true, r, this.multi, i, f, c, h);
      }
      throw new Q(`Graph.${o}: too many arguments (expecting 1, 2 or 3 and got ${arguments.length}).`);
    };
    const a = "some" + n[0].toUpperCase() + n.slice(1, -1);
    e.prototype[a] = function() {
      const l = Array.prototype.slice.call(arguments), c = l.pop();
      return l.push((f, p, y, k, b, I, S) => c(f, p, y, k, b, I, S)), !!this[o].apply(this, l);
    };
    const s = "every" + n[0].toUpperCase() + n.slice(1, -1);
    e.prototype[s] = function() {
      const l = Array.prototype.slice.call(arguments), c = l.pop();
      return l.push((f, p, y, k, b, I, S) => !c(f, p, y, k, b, I, S)), !this[o].apply(this, l);
    };
  }
  function XE(e, t) {
    const { name: n, type: r, direction: i } = t, o = n.slice(0, -1) + "Entries";
    e.prototype[o] = function(a, s) {
      if (r !== "mixed" && this.type !== "mixed" && r !== this.type) return _i();
      if (!arguments.length) return $E(this, r);
      if (arguments.length === 1) {
        a = "" + a;
        const l = this._nodes.get(a);
        if (!l) throw new K(`Graph.${o}: could not find the "${a}" node in the graph.`);
        return HE(r, i, l);
      }
      if (arguments.length === 2) {
        a = "" + a, s = "" + s;
        const l = this._nodes.get(a);
        if (!l) throw new K(`Graph.${o}:  could not find the "${a}" source node in the graph.`);
        if (!this._nodes.has(s)) throw new K(`Graph.${o}:  could not find the "${s}" target node in the graph.`);
        return VE(r, i, l, s);
      }
      throw new Q(`Graph.${o}: too many arguments (expecting 0, 1 or 2 and got ${arguments.length}).`);
    };
  }
  function ZE(e) {
    zE.forEach((t) => {
      KE(e, t), YE(e, t), QE(e, t), XE(e, t);
    });
  }
  const qE = [
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
  function _s() {
    this.A = null, this.B = null;
  }
  _s.prototype.wrap = function(e) {
    this.A === null ? this.A = e : this.B === null && (this.B = e);
  };
  _s.prototype.has = function(e) {
    return this.A !== null && e in this.A || this.B !== null && e in this.B;
  };
  function Bi(e, t, n, r, i) {
    for (const o in r) {
      const a = r[o], s = a.source, l = a.target, c = s === n ? l : s;
      if (t && t.has(c.key)) continue;
      const h = i(c.key, c.attributes);
      if (e && h) return c.key;
    }
  }
  function vc(e, t, n, r, i) {
    if (t !== "mixed") {
      if (t === "undirected") return Bi(e, null, r, r.undirected, i);
      if (typeof n == "string") return Bi(e, null, r, r[n], i);
    }
    const o = new _s();
    let a;
    if (t !== "undirected") {
      if (n !== "out") {
        if (a = Bi(e, null, r, r.in, i), e && a) return a;
        o.wrap(r.in);
      }
      if (n !== "in") {
        if (a = Bi(e, o, r, r.out, i), e && a) return a;
        o.wrap(r.out);
      }
    }
    if (t !== "directed" && (a = Bi(e, o, r, r.undirected, i), e && a)) return a;
  }
  function JE(e, t, n) {
    if (e !== "mixed") {
      if (e === "undirected") return Object.keys(n.undirected);
      if (typeof t == "string") return Object.keys(n[t]);
    }
    const r = [];
    return vc(false, e, t, n, function(i) {
      r.push(i);
    }), r;
  }
  function Mi(e, t, n) {
    const r = Object.keys(n), i = r.length;
    let o = 0;
    return {
      [Symbol.iterator]() {
        return this;
      },
      next() {
        let a = null;
        do {
          if (o >= i) return e && e.wrap(n), {
            done: true
          };
          const s = n[r[o++]], l = s.source, c = s.target;
          if (a = l === t ? c : l, e && e.has(a.key)) {
            a = null;
            continue;
          }
        } while (a === null);
        return {
          done: false,
          value: {
            neighbor: a.key,
            attributes: a.attributes
          }
        };
      }
    };
  }
  function e1(e, t, n) {
    if (e !== "mixed") {
      if (e === "undirected") return Mi(null, n, n.undirected);
      if (typeof t == "string") return Mi(null, n, n[t]);
    }
    let r = _i();
    const i = new _s();
    return e !== "undirected" && (t !== "out" && (r = $n(r, Mi(i, n, n.in))), t !== "in" && (r = $n(r, Mi(i, n, n.out)))), e !== "directed" && (r = $n(r, Mi(i, n, n.undirected))), r;
  }
  function t1(e, t) {
    const { name: n, type: r, direction: i } = t;
    e.prototype[n] = function(o) {
      if (r !== "mixed" && this.type !== "mixed" && r !== this.type) return [];
      o = "" + o;
      const a = this._nodes.get(o);
      if (typeof a > "u") throw new K(`Graph.${n}: could not find the "${o}" node in the graph.`);
      return JE(r === "mixed" ? this.type : r, i, a);
    };
  }
  function n1(e, t) {
    const { name: n, type: r, direction: i } = t, o = "forEach" + n[0].toUpperCase() + n.slice(1, -1);
    e.prototype[o] = function(c, h) {
      if (r !== "mixed" && this.type !== "mixed" && r !== this.type) return;
      c = "" + c;
      const f = this._nodes.get(c);
      if (typeof f > "u") throw new K(`Graph.${o}: could not find the "${c}" node in the graph.`);
      vc(false, r === "mixed" ? this.type : r, i, f, h);
    };
    const a = "map" + n[0].toUpperCase() + n.slice(1);
    e.prototype[a] = function(c, h) {
      const f = [];
      return this[o](c, (p, y) => {
        f.push(h(p, y));
      }), f;
    };
    const s = "filter" + n[0].toUpperCase() + n.slice(1);
    e.prototype[s] = function(c, h) {
      const f = [];
      return this[o](c, (p, y) => {
        h(p, y) && f.push(p);
      }), f;
    };
    const l = "reduce" + n[0].toUpperCase() + n.slice(1);
    e.prototype[l] = function(c, h, f) {
      if (arguments.length < 3) throw new Q(`Graph.${l}: missing initial value. You must provide it because the callback takes more than one argument and we cannot infer the initial value from the first iteration, as you could with a simple array.`);
      let p = f;
      return this[o](c, (y, k) => {
        p = h(p, y, k);
      }), p;
    };
  }
  function r1(e, t) {
    const { name: n, type: r, direction: i } = t, o = n[0].toUpperCase() + n.slice(1, -1), a = "find" + o;
    e.prototype[a] = function(c, h) {
      if (r !== "mixed" && this.type !== "mixed" && r !== this.type) return;
      c = "" + c;
      const f = this._nodes.get(c);
      if (typeof f > "u") throw new K(`Graph.${a}: could not find the "${c}" node in the graph.`);
      return vc(true, r === "mixed" ? this.type : r, i, f, h);
    };
    const s = "some" + o;
    e.prototype[s] = function(c, h) {
      return !!this[a](c, h);
    };
    const l = "every" + o;
    e.prototype[l] = function(c, h) {
      return !this[a](c, (p, y) => !h(p, y));
    };
  }
  function i1(e, t) {
    const { name: n, type: r, direction: i } = t, o = n.slice(0, -1) + "Entries";
    e.prototype[o] = function(a) {
      if (r !== "mixed" && this.type !== "mixed" && r !== this.type) return _i();
      a = "" + a;
      const s = this._nodes.get(a);
      if (typeof s > "u") throw new K(`Graph.${o}: could not find the "${a}" node in the graph.`);
      return e1(r === "mixed" ? this.type : r, i, s);
    };
  }
  function o1(e) {
    qE.forEach((t) => {
      t1(e, t), n1(e, t), r1(e, t), i1(e, t);
    });
  }
  function ia(e, t, n, r, i) {
    const o = r._nodes.values(), a = r.type;
    let s, l, c, h, f, p;
    for (; s = o.next(), s.done !== true; ) {
      let y = false;
      if (l = s.value, a !== "undirected") {
        h = l.out;
        for (c in h) {
          f = h[c];
          do
            p = f.target, y = true, i(l.key, p.key, l.attributes, p.attributes, f.key, f.attributes, f.undirected), f = f.next;
          while (f);
        }
      }
      if (a !== "directed") {
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
  function a1(e, t) {
    const n = {
      key: e
    };
    return _g(t.attributes) || (n.attributes = it({}, t.attributes)), n;
  }
  function s1(e, t, n) {
    const r = {
      key: t,
      source: n.source.key,
      target: n.target.key
    };
    return _g(n.attributes) || (r.attributes = it({}, n.attributes)), e === "mixed" && n.undirected && (r.undirected = true), r;
  }
  function l1(e) {
    if (!ht(e)) throw new Q('Graph.import: invalid serialized node. A serialized node should be a plain object with at least a "key" property.');
    if (!("key" in e)) throw new Q("Graph.import: serialized node is missing its key.");
    if ("attributes" in e && (!ht(e.attributes) || e.attributes === null)) throw new Q("Graph.import: invalid attributes. Attributes should be a plain object, null or omitted.");
  }
  function u1(e) {
    if (!ht(e)) throw new Q('Graph.import: invalid serialized edge. A serialized edge should be a plain object with at least a "source" & "target" property.');
    if (!("source" in e)) throw new Q("Graph.import: serialized edge is missing its source.");
    if (!("target" in e)) throw new Q("Graph.import: serialized edge is missing its target.");
    if ("attributes" in e && (!ht(e.attributes) || e.attributes === null)) throw new Q("Graph.import: invalid attributes. Attributes should be a plain object, null or omitted.");
    if ("undirected" in e && typeof e.undirected != "boolean") throw new Q("Graph.import: invalid undirectedness information. Undirected should be boolean or omitted.");
  }
  const c1 = fE(), d1 = /* @__PURE__ */ new Set([
    "directed",
    "undirected",
    "mixed"
  ]), df = /* @__PURE__ */ new Set([
    "domain",
    "_events",
    "_eventsCount",
    "_maxListeners"
  ]), f1 = [
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
  ], h1 = {
    allowSelfLoops: true,
    multi: false,
    type: "mixed"
  };
  function p1(e, t, n) {
    if (n && !ht(n)) throw new Q(`Graph.addNode: invalid attributes. Expecting an object but got "${n}"`);
    if (t = "" + t, n = n || {}, e._nodes.has(t)) throw new ue(`Graph.addNode: the "${t}" node already exist in the graph.`);
    const r = new e.NodeDataClass(t, n);
    return e._nodes.set(t, r), e.emit("nodeAdded", {
      key: t,
      attributes: n
    }), r;
  }
  function ff(e, t, n) {
    const r = new e.NodeDataClass(t, n);
    return e._nodes.set(t, r), e.emit("nodeAdded", {
      key: t,
      attributes: n
    }), r;
  }
  function Lg(e, t, n, r, i, o, a, s) {
    if (!r && e.type === "undirected") throw new ue(`Graph.${t}: you cannot add a directed edge to an undirected graph. Use the #.addEdge or #.addUndirectedEdge instead.`);
    if (r && e.type === "directed") throw new ue(`Graph.${t}: you cannot add an undirected edge to a directed graph. Use the #.addEdge or #.addDirectedEdge instead.`);
    if (s && !ht(s)) throw new Q(`Graph.${t}: invalid attributes. Expecting an object but got "${s}"`);
    if (o = "" + o, a = "" + a, s = s || {}, !e.allowSelfLoops && o === a) throw new ue(`Graph.${t}: source & target are the same ("${o}"), thus creating a loop explicitly forbidden by this graph 'allowSelfLoops' option set to false.`);
    const l = e._nodes.get(o), c = e._nodes.get(a);
    if (!l) throw new K(`Graph.${t}: source node "${o}" not found.`);
    if (!c) throw new K(`Graph.${t}: target node "${a}" not found.`);
    const h = {
      key: null,
      undirected: r,
      source: o,
      target: a,
      attributes: s
    };
    if (n) i = e._edgeKeyGenerator();
    else if (i = "" + i, e._edges.has(i)) throw new ue(`Graph.${t}: the "${i}" edge already exists in the graph.`);
    if (!e.multi && (r ? typeof l.undirected[a] < "u" : typeof l.out[a] < "u")) throw new ue(`Graph.${t}: an edge linking "${o}" to "${a}" already exists. If you really want to add multiple edges linking those nodes, you should create a multi graph by using the 'multi' option.`);
    const f = new ki(r, i, l, c, s);
    e._edges.set(i, f);
    const p = o === a;
    return r ? (l.undirectedDegree++, c.undirectedDegree++, p && (l.undirectedLoops++, e._undirectedSelfLoopCount++)) : (l.outDegree++, c.inDegree++, p && (l.directedLoops++, e._directedSelfLoopCount++)), e.multi ? f.attachMulti() : f.attach(), r ? e._undirectedSize++ : e._directedSize++, h.key = i, e.emit("edgeAdded", h), i;
  }
  function g1(e, t, n, r, i, o, a, s, l) {
    if (!r && e.type === "undirected") throw new ue(`Graph.${t}: you cannot merge/update a directed edge to an undirected graph. Use the #.mergeEdge/#.updateEdge or #.addUndirectedEdge instead.`);
    if (r && e.type === "directed") throw new ue(`Graph.${t}: you cannot merge/update an undirected edge to a directed graph. Use the #.mergeEdge/#.updateEdge or #.addDirectedEdge instead.`);
    if (s) {
      if (l) {
        if (typeof s != "function") throw new Q(`Graph.${t}: invalid updater function. Expecting a function but got "${s}"`);
      } else if (!ht(s)) throw new Q(`Graph.${t}: invalid attributes. Expecting an object but got "${s}"`);
    }
    o = "" + o, a = "" + a;
    let c;
    if (l && (c = s, s = void 0), !e.allowSelfLoops && o === a) throw new ue(`Graph.${t}: source & target are the same ("${o}"), thus creating a loop explicitly forbidden by this graph 'allowSelfLoops' option set to false.`);
    let h = e._nodes.get(o), f = e._nodes.get(a), p, y;
    if (!n && (p = e._edges.get(i), p)) {
      if ((p.source.key !== o || p.target.key !== a) && (!r || p.source.key !== a || p.target.key !== o)) throw new ue(`Graph.${t}: inconsistency detected when attempting to merge the "${i}" edge with "${o}" source & "${a}" target vs. ("${p.source.key}", "${p.target.key}").`);
      y = p;
    }
    if (!y && !e.multi && h && (y = r ? h.undirected[a] : h.out[a]), y) {
      const m = [
        y.key,
        false,
        false,
        false
      ];
      if (l ? !c : !s) return m;
      if (l) {
        const v = y.attributes;
        y.attributes = c(v), e.emit("edgeAttributesUpdated", {
          type: "replace",
          key: y.key,
          attributes: y.attributes
        });
      } else it(y.attributes, s), e.emit("edgeAttributesUpdated", {
        type: "merge",
        key: y.key,
        attributes: y.attributes,
        data: s
      });
      return m;
    }
    s = s || {}, l && c && (s = c(s));
    const k = {
      key: null,
      undirected: r,
      source: o,
      target: a,
      attributes: s
    };
    if (n) i = e._edgeKeyGenerator();
    else if (i = "" + i, e._edges.has(i)) throw new ue(`Graph.${t}: the "${i}" edge already exists in the graph.`);
    let b = false, I = false;
    h || (h = ff(e, o, {}), b = true, o === a && (f = h, I = true)), f || (f = ff(e, a, {}), I = true), p = new ki(r, i, h, f, s), e._edges.set(i, p);
    const S = o === a;
    return r ? (h.undirectedDegree++, f.undirectedDegree++, S && (h.undirectedLoops++, e._undirectedSelfLoopCount++)) : (h.outDegree++, f.inDegree++, S && (h.directedLoops++, e._directedSelfLoopCount++)), e.multi ? p.attachMulti() : p.attach(), r ? e._undirectedSize++ : e._directedSize++, k.key = i, e.emit("edgeAdded", k), [
      i,
      true,
      b,
      I
    ];
  }
  function Br(e, t) {
    e._edges.delete(t.key);
    const { source: n, target: r, attributes: i } = t, o = t.undirected, a = n === r;
    o ? (n.undirectedDegree--, r.undirectedDegree--, a && (n.undirectedLoops--, e._undirectedSelfLoopCount--)) : (n.outDegree--, r.inDegree--, a && (n.directedLoops--, e._directedSelfLoopCount--)), e.multi ? t.detachMulti() : t.detach(), o ? e._undirectedSize-- : e._directedSize--, e.emit("edgeDropped", {
      key: t.key,
      attributes: i,
      source: n.key,
      target: r.key,
      undirected: o
    });
  }
  class Ie extends wg.EventEmitter {
    constructor(t) {
      if (super(), t = it({}, h1, t), typeof t.multi != "boolean") throw new Q(`Graph.constructor: invalid 'multi' option. Expecting a boolean but got "${t.multi}".`);
      if (!d1.has(t.type)) throw new Q(`Graph.constructor: invalid 'type' option. Should be one of "mixed", "directed" or "undirected" but got "${t.type}".`);
      if (typeof t.allowSelfLoops != "boolean") throw new Q(`Graph.constructor: invalid 'allowSelfLoops' option. Expecting a boolean but got "${t.allowSelfLoops}".`);
      const n = t.type === "mixed" ? kg : t.type === "directed" ? bg : Cg;
      Qt(this, "NodeDataClass", n);
      const r = "geid_" + c1() + "_";
      let i = 0;
      const o = () => {
        let a;
        do
          a = r + i++;
        while (this._edges.has(a));
        return a;
      };
      Qt(this, "_attributes", {}), Qt(this, "_nodes", /* @__PURE__ */ new Map()), Qt(this, "_edges", /* @__PURE__ */ new Map()), Qt(this, "_directedSize", 0), Qt(this, "_undirectedSize", 0), Qt(this, "_directedSelfLoopCount", 0), Qt(this, "_undirectedSelfLoopCount", 0), Qt(this, "_edgeKeyGenerator", o), Qt(this, "_options", t), df.forEach((a) => Qt(this, a, this[a])), fn(this, "order", () => this._nodes.size), fn(this, "size", () => this._edges.size), fn(this, "directedSize", () => this._directedSize), fn(this, "undirectedSize", () => this._undirectedSize), fn(this, "selfLoopCount", () => this._directedSelfLoopCount + this._undirectedSelfLoopCount), fn(this, "directedSelfLoopCount", () => this._directedSelfLoopCount), fn(this, "undirectedSelfLoopCount", () => this._undirectedSelfLoopCount), fn(this, "multi", this._options.multi), fn(this, "type", this._options.type), fn(this, "allowSelfLoops", this._options.allowSelfLoops), fn(this, "implementation", () => "graphology");
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
      throw new Q(`Graph.hasDirectedEdge: invalid arity (${arguments.length}, instead of 1 or 2). You can either ask for an edge id or for the existence of an edge between a source & a target.`);
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
      throw new Q(`Graph.hasDirectedEdge: invalid arity (${arguments.length}, instead of 1 or 2). You can either ask for an edge id or for the existence of an edge between a source & a target.`);
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
      throw new Q(`Graph.hasEdge: invalid arity (${arguments.length}, instead of 1 or 2). You can either ask for an edge id or for the existence of an edge between a source & a target.`);
    }
    directedEdge(t, n) {
      if (this.type === "undirected") return;
      if (t = "" + t, n = "" + n, this.multi) throw new ue("Graph.directedEdge: this method is irrelevant with multigraphs since there might be multiple edges between source & target. See #.directedEdges instead.");
      const r = this._nodes.get(t);
      if (!r) throw new K(`Graph.directedEdge: could not find the "${t}" source node in the graph.`);
      if (!this._nodes.has(n)) throw new K(`Graph.directedEdge: could not find the "${n}" target node in the graph.`);
      const i = r.out && r.out[n] || void 0;
      if (i) return i.key;
    }
    undirectedEdge(t, n) {
      if (this.type === "directed") return;
      if (t = "" + t, n = "" + n, this.multi) throw new ue("Graph.undirectedEdge: this method is irrelevant with multigraphs since there might be multiple edges between source & target. See #.undirectedEdges instead.");
      const r = this._nodes.get(t);
      if (!r) throw new K(`Graph.undirectedEdge: could not find the "${t}" source node in the graph.`);
      if (!this._nodes.has(n)) throw new K(`Graph.undirectedEdge: could not find the "${n}" target node in the graph.`);
      const i = r.undirected && r.undirected[n] || void 0;
      if (i) return i.key;
    }
    edge(t, n) {
      if (this.multi) throw new ue("Graph.edge: this method is irrelevant with multigraphs since there might be multiple edges between source & target. See #.edges instead.");
      t = "" + t, n = "" + n;
      const r = this._nodes.get(t);
      if (!r) throw new K(`Graph.edge: could not find the "${t}" source node in the graph.`);
      if (!this._nodes.has(n)) throw new K(`Graph.edge: could not find the "${n}" target node in the graph.`);
      const i = r.out && r.out[n] || r.undirected && r.undirected[n] || void 0;
      if (i) return i.key;
    }
    areDirectedNeighbors(t, n) {
      t = "" + t, n = "" + n;
      const r = this._nodes.get(t);
      if (!r) throw new K(`Graph.areDirectedNeighbors: could not find the "${t}" node in the graph.`);
      return this.type === "undirected" ? false : n in r.in || n in r.out;
    }
    areOutNeighbors(t, n) {
      t = "" + t, n = "" + n;
      const r = this._nodes.get(t);
      if (!r) throw new K(`Graph.areOutNeighbors: could not find the "${t}" node in the graph.`);
      return this.type === "undirected" ? false : n in r.out;
    }
    areInNeighbors(t, n) {
      t = "" + t, n = "" + n;
      const r = this._nodes.get(t);
      if (!r) throw new K(`Graph.areInNeighbors: could not find the "${t}" node in the graph.`);
      return this.type === "undirected" ? false : n in r.in;
    }
    areUndirectedNeighbors(t, n) {
      t = "" + t, n = "" + n;
      const r = this._nodes.get(t);
      if (!r) throw new K(`Graph.areUndirectedNeighbors: could not find the "${t}" node in the graph.`);
      return this.type === "directed" ? false : n in r.undirected;
    }
    areNeighbors(t, n) {
      t = "" + t, n = "" + n;
      const r = this._nodes.get(t);
      if (!r) throw new K(`Graph.areNeighbors: could not find the "${t}" node in the graph.`);
      return this.type !== "undirected" && (n in r.in || n in r.out) || this.type !== "directed" && n in r.undirected;
    }
    areInboundNeighbors(t, n) {
      t = "" + t, n = "" + n;
      const r = this._nodes.get(t);
      if (!r) throw new K(`Graph.areInboundNeighbors: could not find the "${t}" node in the graph.`);
      return this.type !== "undirected" && n in r.in || this.type !== "directed" && n in r.undirected;
    }
    areOutboundNeighbors(t, n) {
      t = "" + t, n = "" + n;
      const r = this._nodes.get(t);
      if (!r) throw new K(`Graph.areOutboundNeighbors: could not find the "${t}" node in the graph.`);
      return this.type !== "undirected" && n in r.out || this.type !== "directed" && n in r.undirected;
    }
    inDegree(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new K(`Graph.inDegree: could not find the "${t}" node in the graph.`);
      return this.type === "undirected" ? 0 : n.inDegree;
    }
    outDegree(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new K(`Graph.outDegree: could not find the "${t}" node in the graph.`);
      return this.type === "undirected" ? 0 : n.outDegree;
    }
    directedDegree(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new K(`Graph.directedDegree: could not find the "${t}" node in the graph.`);
      return this.type === "undirected" ? 0 : n.inDegree + n.outDegree;
    }
    undirectedDegree(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new K(`Graph.undirectedDegree: could not find the "${t}" node in the graph.`);
      return this.type === "directed" ? 0 : n.undirectedDegree;
    }
    inboundDegree(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new K(`Graph.inboundDegree: could not find the "${t}" node in the graph.`);
      let r = 0;
      return this.type !== "directed" && (r += n.undirectedDegree), this.type !== "undirected" && (r += n.inDegree), r;
    }
    outboundDegree(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new K(`Graph.outboundDegree: could not find the "${t}" node in the graph.`);
      let r = 0;
      return this.type !== "directed" && (r += n.undirectedDegree), this.type !== "undirected" && (r += n.outDegree), r;
    }
    degree(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new K(`Graph.degree: could not find the "${t}" node in the graph.`);
      let r = 0;
      return this.type !== "directed" && (r += n.undirectedDegree), this.type !== "undirected" && (r += n.inDegree + n.outDegree), r;
    }
    inDegreeWithoutSelfLoops(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new K(`Graph.inDegreeWithoutSelfLoops: could not find the "${t}" node in the graph.`);
      return this.type === "undirected" ? 0 : n.inDegree - n.directedLoops;
    }
    outDegreeWithoutSelfLoops(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new K(`Graph.outDegreeWithoutSelfLoops: could not find the "${t}" node in the graph.`);
      return this.type === "undirected" ? 0 : n.outDegree - n.directedLoops;
    }
    directedDegreeWithoutSelfLoops(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new K(`Graph.directedDegreeWithoutSelfLoops: could not find the "${t}" node in the graph.`);
      return this.type === "undirected" ? 0 : n.inDegree + n.outDegree - n.directedLoops * 2;
    }
    undirectedDegreeWithoutSelfLoops(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new K(`Graph.undirectedDegreeWithoutSelfLoops: could not find the "${t}" node in the graph.`);
      return this.type === "directed" ? 0 : n.undirectedDegree - n.undirectedLoops * 2;
    }
    inboundDegreeWithoutSelfLoops(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new K(`Graph.inboundDegreeWithoutSelfLoops: could not find the "${t}" node in the graph.`);
      let r = 0, i = 0;
      return this.type !== "directed" && (r += n.undirectedDegree, i += n.undirectedLoops * 2), this.type !== "undirected" && (r += n.inDegree, i += n.directedLoops), r - i;
    }
    outboundDegreeWithoutSelfLoops(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new K(`Graph.outboundDegreeWithoutSelfLoops: could not find the "${t}" node in the graph.`);
      let r = 0, i = 0;
      return this.type !== "directed" && (r += n.undirectedDegree, i += n.undirectedLoops * 2), this.type !== "undirected" && (r += n.outDegree, i += n.directedLoops), r - i;
    }
    degreeWithoutSelfLoops(t) {
      t = "" + t;
      const n = this._nodes.get(t);
      if (!n) throw new K(`Graph.degreeWithoutSelfLoops: could not find the "${t}" node in the graph.`);
      let r = 0, i = 0;
      return this.type !== "directed" && (r += n.undirectedDegree, i += n.undirectedLoops * 2), this.type !== "undirected" && (r += n.inDegree + n.outDegree, i += n.directedLoops * 2), r - i;
    }
    source(t) {
      t = "" + t;
      const n = this._edges.get(t);
      if (!n) throw new K(`Graph.source: could not find the "${t}" edge in the graph.`);
      return n.source.key;
    }
    target(t) {
      t = "" + t;
      const n = this._edges.get(t);
      if (!n) throw new K(`Graph.target: could not find the "${t}" edge in the graph.`);
      return n.target.key;
    }
    extremities(t) {
      t = "" + t;
      const n = this._edges.get(t);
      if (!n) throw new K(`Graph.extremities: could not find the "${t}" edge in the graph.`);
      return [
        n.source.key,
        n.target.key
      ];
    }
    opposite(t, n) {
      t = "" + t, n = "" + n;
      const r = this._edges.get(n);
      if (!r) throw new K(`Graph.opposite: could not find the "${n}" edge in the graph.`);
      const i = r.source.key, o = r.target.key;
      if (t === i) return o;
      if (t === o) return i;
      throw new K(`Graph.opposite: the "${t}" node is not attached to the "${n}" edge (${i}, ${o}).`);
    }
    hasExtremity(t, n) {
      t = "" + t, n = "" + n;
      const r = this._edges.get(t);
      if (!r) throw new K(`Graph.hasExtremity: could not find the "${t}" edge in the graph.`);
      return r.source.key === n || r.target.key === n;
    }
    isUndirected(t) {
      t = "" + t;
      const n = this._edges.get(t);
      if (!n) throw new K(`Graph.isUndirected: could not find the "${t}" edge in the graph.`);
      return n.undirected;
    }
    isDirected(t) {
      t = "" + t;
      const n = this._edges.get(t);
      if (!n) throw new K(`Graph.isDirected: could not find the "${t}" edge in the graph.`);
      return !n.undirected;
    }
    isSelfLoop(t) {
      t = "" + t;
      const n = this._edges.get(t);
      if (!n) throw new K(`Graph.isSelfLoop: could not find the "${t}" edge in the graph.`);
      return n.source === n.target;
    }
    addNode(t, n) {
      return p1(this, t, n).key;
    }
    mergeNode(t, n) {
      if (n && !ht(n)) throw new Q(`Graph.mergeNode: invalid attributes. Expecting an object but got "${n}"`);
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
      if (n && typeof n != "function") throw new Q(`Graph.updateNode: invalid updater function. Expecting a function but got "${n}"`);
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
      if (!n) throw new K(`Graph.dropNode: could not find the "${t}" node in the graph.`);
      let r;
      if (this.type !== "undirected") {
        for (const i in n.out) {
          r = n.out[i];
          do
            Br(this, r), r = r.next;
          while (r);
        }
        for (const i in n.in) {
          r = n.in[i];
          do
            Br(this, r), r = r.next;
          while (r);
        }
      }
      if (this.type !== "directed") for (const i in n.undirected) {
        r = n.undirected[i];
        do
          Br(this, r), r = r.next;
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
        if (n = nn(this, r, i, this.type), !n) throw new K(`Graph.dropEdge: could not find the "${r}" -> "${i}" edge in the graph.`);
      } else if (t = "" + t, n = this._edges.get(t), !n) throw new K(`Graph.dropEdge: could not find the "${t}" edge in the graph.`);
      return Br(this, n), this;
    }
    dropDirectedEdge(t, n) {
      if (arguments.length < 2) throw new ue("Graph.dropDirectedEdge: it does not make sense to try and drop a directed edge by key. What if the edge with this key is undirected? Use #.dropEdge for this purpose instead.");
      if (this.multi) throw new ue("Graph.dropDirectedEdge: cannot use a {source,target} combo when dropping an edge in a MultiGraph since we cannot infer the one you want to delete as there could be multiple ones.");
      t = "" + t, n = "" + n;
      const r = nn(this, t, n, "directed");
      if (!r) throw new K(`Graph.dropDirectedEdge: could not find a "${t}" -> "${n}" edge in the graph.`);
      return Br(this, r), this;
    }
    dropUndirectedEdge(t, n) {
      if (arguments.length < 2) throw new ue("Graph.dropUndirectedEdge: it does not make sense to drop a directed edge by key. What if the edge with this key is undirected? Use #.dropEdge for this purpose instead.");
      if (this.multi) throw new ue("Graph.dropUndirectedEdge: cannot use a {source,target} combo when dropping an edge in a MultiGraph since we cannot infer the one you want to delete as there could be multiple ones.");
      const r = nn(this, t, n, "undirected");
      if (!r) throw new K(`Graph.dropUndirectedEdge: could not find a "${t}" -> "${n}" edge in the graph.`);
      return Br(this, r), this;
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
      if (typeof n != "function") throw new Q("Graph.updateAttribute: updater should be a function.");
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
      if (!ht(t)) throw new Q("Graph.replaceAttributes: provided attributes are not a plain object.");
      return this._attributes = t, this.emit("attributesUpdated", {
        type: "replace",
        attributes: this._attributes
      }), this;
    }
    mergeAttributes(t) {
      if (!ht(t)) throw new Q("Graph.mergeAttributes: provided attributes are not a plain object.");
      return it(this._attributes, t), this.emit("attributesUpdated", {
        type: "merge",
        attributes: this._attributes,
        data: t
      }), this;
    }
    updateAttributes(t) {
      if (typeof t != "function") throw new Q("Graph.updateAttributes: provided updater is not a function.");
      return this._attributes = t(this._attributes), this.emit("attributesUpdated", {
        type: "update",
        attributes: this._attributes
      }), this;
    }
    updateEachNodeAttributes(t, n) {
      if (typeof t != "function") throw new Q("Graph.updateEachNodeAttributes: expecting an updater function.");
      if (n && !cf(n)) throw new Q("Graph.updateEachNodeAttributes: invalid hints. Expecting an object having the following shape: {attributes?: [string]}");
      const r = this._nodes.values();
      let i, o;
      for (; i = r.next(), i.done !== true; ) o = i.value, o.attributes = t(o.key, o.attributes);
      this.emit("eachNodeAttributesUpdated", {
        hints: n || null
      });
    }
    updateEachEdgeAttributes(t, n) {
      if (typeof t != "function") throw new Q("Graph.updateEachEdgeAttributes: expecting an updater function.");
      if (n && !cf(n)) throw new Q("Graph.updateEachEdgeAttributes: invalid hints. Expecting an object having the following shape: {attributes?: [string]}");
      const r = this._edges.values();
      let i, o, a, s;
      for (; i = r.next(), i.done !== true; ) o = i.value, a = o.source, s = o.target, o.attributes = t(o.key, o.attributes, a.key, s.key, a.attributes, s.attributes, o.undirected);
      this.emit("eachEdgeAttributesUpdated", {
        hints: n || null
      });
    }
    forEachAdjacencyEntry(t) {
      if (typeof t != "function") throw new Q("Graph.forEachAdjacencyEntry: expecting a callback.");
      ia(false, false, false, this, t);
    }
    forEachAdjacencyEntryWithOrphans(t) {
      if (typeof t != "function") throw new Q("Graph.forEachAdjacencyEntryWithOrphans: expecting a callback.");
      ia(false, false, true, this, t);
    }
    forEachAssymetricAdjacencyEntry(t) {
      if (typeof t != "function") throw new Q("Graph.forEachAssymetricAdjacencyEntry: expecting a callback.");
      ia(false, true, false, this, t);
    }
    forEachAssymetricAdjacencyEntryWithOrphans(t) {
      if (typeof t != "function") throw new Q("Graph.forEachAssymetricAdjacencyEntryWithOrphans: expecting a callback.");
      ia(false, true, true, this, t);
    }
    nodes() {
      return Array.from(this._nodes.keys());
    }
    forEachNode(t) {
      if (typeof t != "function") throw new Q("Graph.forEachNode: expecting a callback.");
      const n = this._nodes.values();
      let r, i;
      for (; r = n.next(), r.done !== true; ) i = r.value, t(i.key, i.attributes);
    }
    findNode(t) {
      if (typeof t != "function") throw new Q("Graph.findNode: expecting a callback.");
      const n = this._nodes.values();
      let r, i;
      for (; r = n.next(), r.done !== true; ) if (i = r.value, t(i.key, i.attributes)) return i.key;
    }
    mapNodes(t) {
      if (typeof t != "function") throw new Q("Graph.mapNode: expecting a callback.");
      const n = this._nodes.values();
      let r, i;
      const o = new Array(this.order);
      let a = 0;
      for (; r = n.next(), r.done !== true; ) i = r.value, o[a++] = t(i.key, i.attributes);
      return o;
    }
    someNode(t) {
      if (typeof t != "function") throw new Q("Graph.someNode: expecting a callback.");
      const n = this._nodes.values();
      let r, i;
      for (; r = n.next(), r.done !== true; ) if (i = r.value, t(i.key, i.attributes)) return true;
      return false;
    }
    everyNode(t) {
      if (typeof t != "function") throw new Q("Graph.everyNode: expecting a callback.");
      const n = this._nodes.values();
      let r, i;
      for (; r = n.next(), r.done !== true; ) if (i = r.value, !t(i.key, i.attributes)) return false;
      return true;
    }
    filterNodes(t) {
      if (typeof t != "function") throw new Q("Graph.filterNodes: expecting a callback.");
      const n = this._nodes.values();
      let r, i;
      const o = [];
      for (; r = n.next(), r.done !== true; ) i = r.value, t(i.key, i.attributes) && o.push(i.key);
      return o;
    }
    reduceNodes(t, n) {
      if (typeof t != "function") throw new Q("Graph.reduceNodes: expecting a callback.");
      if (arguments.length < 2) throw new Q("Graph.reduceNodes: missing initial value. You must provide it because the callback takes more than one argument and we cannot infer the initial value from the first iteration, as you could with a simple array.");
      let r = n;
      const i = this._nodes.values();
      let o, a;
      for (; o = i.next(), o.done !== true; ) a = o.value, r = t(r, a.key, a.attributes);
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
        t[n++] = a1(o, i);
      });
      const r = new Array(this._edges.size);
      return n = 0, this._edges.forEach((i, o) => {
        r[n++] = s1(this.type, o, i);
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
      if (t instanceof Ie) return t.forEachNode((l, c) => {
        n ? this.mergeNode(l, c) : this.addNode(l, c);
      }), t.forEachEdge((l, c, h, f, p, y, k) => {
        n ? k ? this.mergeUndirectedEdgeWithKey(l, h, f, c) : this.mergeDirectedEdgeWithKey(l, h, f, c) : k ? this.addUndirectedEdgeWithKey(l, h, f, c) : this.addDirectedEdgeWithKey(l, h, f, c);
      }), this;
      if (!ht(t)) throw new Q("Graph.import: invalid argument. Expecting a serialized graph or, alternatively, a Graph instance.");
      if (t.attributes) {
        if (!ht(t.attributes)) throw new Q("Graph.import: invalid attributes. Expecting a plain object.");
        n ? this.mergeAttributes(t.attributes) : this.replaceAttributes(t.attributes);
      }
      let r, i, o, a, s;
      if (t.nodes) {
        if (o = t.nodes, !Array.isArray(o)) throw new Q("Graph.import: invalid nodes. Expecting an array.");
        for (r = 0, i = o.length; r < i; r++) {
          a = o[r], l1(a);
          const { key: l, attributes: c } = a;
          n ? this.mergeNode(l, c) : this.addNode(l, c);
        }
      }
      if (t.edges) {
        let l = false;
        if (this.type === "undirected" && (l = true), o = t.edges, !Array.isArray(o)) throw new Q("Graph.import: invalid edges. Expecting an array.");
        for (r = 0, i = o.length; r < i; r++) {
          s = o[r], u1(s);
          const { source: c, target: h, attributes: f, undirected: p = l } = s;
          let y;
          "key" in s ? (y = n ? p ? this.mergeUndirectedEdgeWithKey : this.mergeDirectedEdgeWithKey : p ? this.addUndirectedEdgeWithKey : this.addDirectedEdgeWithKey, y.call(this, s.key, c, h, f)) : (y = n ? p ? this.mergeUndirectedEdge : this.mergeDirectedEdge : p ? this.addUndirectedEdge : this.addDirectedEdge, y.call(this, c, h, f));
        }
      }
      return this;
    }
    nullCopy(t) {
      const n = new Ie(it({}, this._options, t));
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
      if (t = t || {}, typeof t.type == "string" && t.type !== this.type && t.type !== "mixed") throw new ue(`Graph.copy: cannot create an incompatible copy from "${this.type}" type to "${t.type}" because this would mean losing information about the current graph.`);
      if (typeof t.multi == "boolean" && t.multi !== this.multi && t.multi !== true) throw new ue("Graph.copy: cannot create an incompatible copy by downgrading a multi graph to a simple one because this would mean losing information about the current graph.");
      if (typeof t.allowSelfLoops == "boolean" && t.allowSelfLoops !== this.allowSelfLoops && t.allowSelfLoops !== true) throw new ue("Graph.copy: cannot create an incompatible copy from a graph allowing self loops to one that does not because this would mean losing information about the current graph.");
      const n = this.emptyCopy(t), r = this._edges.values();
      let i, o;
      for (; i = r.next(), i.done !== true; ) o = i.value, Lg(n, "copy", false, o.undirected, o.key, o.source.key, o.target.key, it({}, o.attributes));
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
      this._nodes.forEach((o, a) => {
        t[a] = o.attributes;
      });
      const n = {}, r = {};
      this._edges.forEach((o, a) => {
        const s = o.undirected ? "--" : "->";
        let l = "", c = o.source.key, h = o.target.key, f;
        o.undirected && c > h && (f = c, c = h, h = f);
        const p = `(${c})${s}(${h})`;
        a.startsWith("geid_") ? this.multi && (typeof r[p] > "u" ? r[p] = 0 : r[p]++, l += `${r[p]}. `) : l += `[${a}]: `, l += p, n[l] = o.attributes;
      });
      const i = {};
      for (const o in this) this.hasOwnProperty(o) && !df.has(o) && typeof this[o] != "function" && typeof o != "symbol" && (i[o] = this[o]);
      return i.attributes = this._attributes, i.nodes = t, i.edges = n, Qt(i, "constructor", this.constructor), i;
    }
  }
  typeof Symbol < "u" && (Ie.prototype[Symbol.for("nodejs.util.inspect.custom")] = Ie.prototype.inspect);
  f1.forEach((e) => {
    [
      "add",
      "merge",
      "update"
    ].forEach((t) => {
      const n = e.name(t), r = t === "add" ? Lg : g1;
      e.generateKey ? Ie.prototype[n] = function(i, o, a) {
        return r(this, n, true, (e.type || this.type) === "undirected", null, i, o, a, t === "update");
      } : Ie.prototype[n] = function(i, o, a, s) {
        return r(this, n, false, (e.type || this.type) === "undirected", i, o, a, s, t === "update");
      };
    });
  });
  bE(Ie);
  NE(Ie);
  ZE(Ie);
  o1(Ie);
  class Dg extends Ie {
    constructor(t) {
      const n = it({
        type: "directed"
      }, t);
      if ("multi" in n && n.multi !== false) throw new Q("DirectedGraph.from: inconsistent indication that the graph should be multi in given options!");
      if (n.type !== "directed") throw new Q('DirectedGraph.from: inconsistent "' + n.type + '" type in given options!');
      super(n);
    }
  }
  class Pg extends Ie {
    constructor(t) {
      const n = it({
        type: "undirected"
      }, t);
      if ("multi" in n && n.multi !== false) throw new Q("UndirectedGraph.from: inconsistent indication that the graph should be multi in given options!");
      if (n.type !== "undirected") throw new Q('UndirectedGraph.from: inconsistent "' + n.type + '" type in given options!');
      super(n);
    }
  }
  class Ig extends Ie {
    constructor(t) {
      const n = it({
        multi: true
      }, t);
      if ("multi" in n && n.multi !== true) throw new Q("MultiGraph.from: inconsistent indication that the graph should be simple in given options!");
      super(n);
    }
  }
  class Fg extends Ie {
    constructor(t) {
      const n = it({
        type: "directed",
        multi: true
      }, t);
      if ("multi" in n && n.multi !== true) throw new Q("MultiDirectedGraph.from: inconsistent indication that the graph should be simple in given options!");
      if (n.type !== "directed") throw new Q('MultiDirectedGraph.from: inconsistent "' + n.type + '" type in given options!');
      super(n);
    }
  }
  class Ng extends Ie {
    constructor(t) {
      const n = it({
        type: "undirected",
        multi: true
      }, t);
      if ("multi" in n && n.multi !== true) throw new Q("MultiUndirectedGraph.from: inconsistent indication that the graph should be simple in given options!");
      if (n.type !== "undirected") throw new Q('MultiUndirectedGraph.from: inconsistent "' + n.type + '" type in given options!');
      super(n);
    }
  }
  function bi(e) {
    e.from = function(t, n) {
      const r = it({}, t.options, n), i = new e(r);
      return i.import(t), i;
    };
  }
  bi(Ie);
  bi(Dg);
  bi(Pg);
  bi(Ig);
  bi(Fg);
  bi(Ng);
  Ie.Graph = Ie;
  Ie.DirectedGraph = Dg;
  Ie.UndirectedGraph = Pg;
  Ie.MultiGraph = Ig;
  Ie.MultiDirectedGraph = Fg;
  Ie.MultiUndirectedGraph = Ng;
  Ie.InvalidArgumentsGraphError = Q;
  Ie.NotFoundGraphError = K;
  Ie.UsageGraphError = ue;
  var m1 = function() {
    var t, n, r = {};
    (function() {
      var o = 0, a = 1, s = 2, l = 3, c = 4, h = 5, f = 6, p = 7, y = 8, k = 9, b = 0, I = 1, S = 2, m = 0, v = 1, E = 2, A = 3, F = 4, R = 5, L = 6, x = 7, G = 8, V = 3, B = 10, W = 3, O = 9, re = 10;
      r.exports = function(te, _, $) {
        var H, D, C, Y, ie, _e, Se, oe, X, Qe, ze = _.length, _n = $.length, at = te.adjustSizes, mt = te.barnesHutTheta * te.barnesHutTheta, Xe, me, ve, he, vt, se, ae, U = [];
        for (C = 0; C < ze; C += B) _[C + c] = _[C + s], _[C + h] = _[C + l], _[C + s] = 0, _[C + l] = 0;
        if (te.outboundAttractionDistribution) {
          for (Xe = 0, C = 0; C < ze; C += B) Xe += _[C + f];
          Xe /= ze / B;
        }
        if (te.barnesHutOptimize) {
          var He = 1 / 0, It = -1 / 0, ln = 1 / 0, st = -1 / 0, yt, g, u;
          for (C = 0; C < ze; C += B) He = Math.min(He, _[C + o]), It = Math.max(It, _[C + o]), ln = Math.min(ln, _[C + a]), st = Math.max(st, _[C + a]);
          var d = It - He, w = st - ln;
          for (d > w ? (ln -= (d - w) / 2, st = ln + d) : (He -= (w - d) / 2, It = He + w), U[0 + m] = -1, U[0 + v] = (He + It) / 2, U[0 + E] = (ln + st) / 2, U[0 + A] = Math.max(It - He, st - ln), U[0 + F] = -1, U[0 + R] = -1, U[0 + L] = 0, U[0 + x] = 0, U[0 + G] = 0, H = 1, C = 0; C < ze; C += B) for (D = 0, u = V; ; ) if (U[D + R] >= 0) {
            _[C + o] < U[D + v] ? _[C + a] < U[D + E] ? yt = U[D + R] : yt = U[D + R] + O : _[C + a] < U[D + E] ? yt = U[D + R] + O * 2 : yt = U[D + R] + O * 3, U[D + x] = (U[D + x] * U[D + L] + _[C + o] * _[C + f]) / (U[D + L] + _[C + f]), U[D + G] = (U[D + G] * U[D + L] + _[C + a] * _[C + f]) / (U[D + L] + _[C + f]), U[D + L] += _[C + f], D = yt;
            continue;
          } else if (U[D + m] < 0) {
            U[D + m] = C;
            break;
          } else {
            if (U[D + R] = H * O, oe = U[D + A] / 2, X = U[D + R], U[X + m] = -1, U[X + v] = U[D + v] - oe, U[X + E] = U[D + E] - oe, U[X + A] = oe, U[X + F] = X + O, U[X + R] = -1, U[X + L] = 0, U[X + x] = 0, U[X + G] = 0, X += O, U[X + m] = -1, U[X + v] = U[D + v] - oe, U[X + E] = U[D + E] + oe, U[X + A] = oe, U[X + F] = X + O, U[X + R] = -1, U[X + L] = 0, U[X + x] = 0, U[X + G] = 0, X += O, U[X + m] = -1, U[X + v] = U[D + v] + oe, U[X + E] = U[D + E] - oe, U[X + A] = oe, U[X + F] = X + O, U[X + R] = -1, U[X + L] = 0, U[X + x] = 0, U[X + G] = 0, X += O, U[X + m] = -1, U[X + v] = U[D + v] + oe, U[X + E] = U[D + E] + oe, U[X + A] = oe, U[X + F] = U[D + F], U[X + R] = -1, U[X + L] = 0, U[X + x] = 0, U[X + G] = 0, H += 4, _[U[D + m] + o] < U[D + v] ? _[U[D + m] + a] < U[D + E] ? yt = U[D + R] : yt = U[D + R] + O : _[U[D + m] + a] < U[D + E] ? yt = U[D + R] + O * 2 : yt = U[D + R] + O * 3, U[D + L] = _[U[D + m] + f], U[D + x] = _[U[D + m] + o], U[D + G] = _[U[D + m] + a], U[yt + m] = U[D + m], U[D + m] = -1, _[C + o] < U[D + v] ? _[C + a] < U[D + E] ? g = U[D + R] : g = U[D + R] + O : _[C + a] < U[D + E] ? g = U[D + R] + O * 2 : g = U[D + R] + O * 3, yt === g) if (u--) {
              D = yt;
              continue;
            } else {
              u = V;
              break;
            }
            U[g + m] = C;
            break;
          }
        }
        if (te.barnesHutOptimize) for (me = te.scalingRatio, C = 0; C < ze; C += B) for (D = 0; ; ) if (U[D + R] >= 0) if (se = Math.pow(_[C + o] - U[D + x], 2) + Math.pow(_[C + a] - U[D + G], 2), Qe = U[D + A], 4 * Qe * Qe / se < mt) {
          if (ve = _[C + o] - U[D + x], he = _[C + a] - U[D + G], at === true ? se > 0 ? (ae = me * _[C + f] * U[D + L] / se, _[C + s] += ve * ae, _[C + l] += he * ae) : se < 0 && (ae = -me * _[C + f] * U[D + L] / Math.sqrt(se), _[C + s] += ve * ae, _[C + l] += he * ae) : se > 0 && (ae = me * _[C + f] * U[D + L] / se, _[C + s] += ve * ae, _[C + l] += he * ae), D = U[D + F], D < 0) break;
          continue;
        } else {
          D = U[D + R];
          continue;
        }
        else {
          if (_e = U[D + m], _e >= 0 && _e !== C && (ve = _[C + o] - _[_e + o], he = _[C + a] - _[_e + a], se = ve * ve + he * he, at === true ? se > 0 ? (ae = me * _[C + f] * _[_e + f] / se, _[C + s] += ve * ae, _[C + l] += he * ae) : se < 0 && (ae = -me * _[C + f] * _[_e + f] / Math.sqrt(se), _[C + s] += ve * ae, _[C + l] += he * ae) : se > 0 && (ae = me * _[C + f] * _[_e + f] / se, _[C + s] += ve * ae, _[C + l] += he * ae)), D = U[D + F], D < 0) break;
          continue;
        }
        else for (me = te.scalingRatio, Y = 0; Y < ze; Y += B) for (ie = 0; ie < Y; ie += B) ve = _[Y + o] - _[ie + o], he = _[Y + a] - _[ie + a], at === true ? (se = Math.sqrt(ve * ve + he * he) - _[Y + y] - _[ie + y], se > 0 ? (ae = me * _[Y + f] * _[ie + f] / se / se, _[Y + s] += ve * ae, _[Y + l] += he * ae, _[ie + s] -= ve * ae, _[ie + l] -= he * ae) : se < 0 && (ae = 100 * me * _[Y + f] * _[ie + f], _[Y + s] += ve * ae, _[Y + l] += he * ae, _[ie + s] -= ve * ae, _[ie + l] -= he * ae)) : (se = Math.sqrt(ve * ve + he * he), se > 0 && (ae = me * _[Y + f] * _[ie + f] / se / se, _[Y + s] += ve * ae, _[Y + l] += he * ae, _[ie + s] -= ve * ae, _[ie + l] -= he * ae));
        for (X = te.gravity / te.scalingRatio, me = te.scalingRatio, C = 0; C < ze; C += B) ae = 0, ve = _[C + o], he = _[C + a], se = Math.sqrt(Math.pow(ve, 2) + Math.pow(he, 2)), te.strongGravityMode ? se > 0 && (ae = me * _[C + f] * X) : se > 0 && (ae = me * _[C + f] * X / se), _[C + s] -= ve * ae, _[C + l] -= he * ae;
        for (me = 1 * (te.outboundAttractionDistribution ? Xe : 1), Se = 0; Se < _n; Se += W) Y = $[Se + b], ie = $[Se + I], oe = $[Se + S], vt = Math.pow(oe, te.edgeWeightInfluence), ve = _[Y + o] - _[ie + o], he = _[Y + a] - _[ie + a], at === true ? (se = Math.sqrt(ve * ve + he * he) - _[Y + y] - _[ie + y], te.linLogMode ? te.outboundAttractionDistribution ? se > 0 && (ae = -me * vt * Math.log(1 + se) / se / _[Y + f]) : se > 0 && (ae = -me * vt * Math.log(1 + se) / se) : te.outboundAttractionDistribution ? se > 0 && (ae = -me * vt / _[Y + f]) : se > 0 && (ae = -me * vt)) : (se = Math.sqrt(Math.pow(ve, 2) + Math.pow(he, 2)), te.linLogMode ? te.outboundAttractionDistribution ? se > 0 && (ae = -me * vt * Math.log(1 + se) / se / _[Y + f]) : se > 0 && (ae = -me * vt * Math.log(1 + se) / se) : te.outboundAttractionDistribution ? (se = 1, ae = -me * vt / _[Y + f]) : (se = 1, ae = -me * vt)), se > 0 && (_[Y + s] += ve * ae, _[Y + l] += he * ae, _[ie + s] -= ve * ae, _[ie + l] -= he * ae);
        var T, P, z, de, ke, xe;
        if (at === true) for (C = 0; C < ze; C += B) _[C + k] !== 1 && (T = Math.sqrt(Math.pow(_[C + s], 2) + Math.pow(_[C + l], 2)), T > re && (_[C + s] = _[C + s] * re / T, _[C + l] = _[C + l] * re / T), P = _[C + f] * Math.sqrt((_[C + c] - _[C + s]) * (_[C + c] - _[C + s]) + (_[C + h] - _[C + l]) * (_[C + h] - _[C + l])), z = Math.sqrt((_[C + c] + _[C + s]) * (_[C + c] + _[C + s]) + (_[C + h] + _[C + l]) * (_[C + h] + _[C + l])) / 2, de = 0.1 * Math.log(1 + z) / (1 + Math.sqrt(P)), ke = _[C + o] + _[C + s] * (de / te.slowDown), _[C + o] = ke, xe = _[C + a] + _[C + l] * (de / te.slowDown), _[C + a] = xe);
        else for (C = 0; C < ze; C += B) _[C + k] !== 1 && (P = _[C + f] * Math.sqrt((_[C + c] - _[C + s]) * (_[C + c] - _[C + s]) + (_[C + h] - _[C + l]) * (_[C + h] - _[C + l])), z = Math.sqrt((_[C + c] + _[C + s]) * (_[C + c] + _[C + s]) + (_[C + h] + _[C + l]) * (_[C + h] + _[C + l])) / 2, de = _[C + p] * Math.log(1 + z) / (1 + Math.sqrt(P)), _[C + p] = Math.min(1, Math.sqrt(de * (Math.pow(_[C + s], 2) + Math.pow(_[C + l], 2)) / (1 + Math.sqrt(P)))), ke = _[C + o] + _[C + s] * (de / te.slowDown), _[C + o] = ke, xe = _[C + a] + _[C + l] * (de / te.slowDown), _[C + a] = xe);
        return {};
      };
    })();
    var i = r.exports;
    self.addEventListener("message", function(o) {
      var a = o.data;
      t = new Float32Array(a.nodes), a.edges && (n = new Float32Array(a.edges)), i(a.settings, t, n), self.postMessage({
        nodes: t.buffer
      }, [
        t.buffer
      ]);
    });
  }, Po = {};
  function v1(e) {
    return typeof e != "number" || isNaN(e) ? 1 : e;
  }
  function y1(e, t) {
    var n = {}, r = function(a) {
      return typeof a > "u" ? t : a;
    };
    typeof t == "function" && (r = t);
    var i = function(a) {
      return r(a[e]);
    }, o = function() {
      return r(void 0);
    };
    return typeof e == "string" ? (n.fromAttributes = i, n.fromGraph = function(a, s) {
      return i(a.getNodeAttributes(s));
    }, n.fromEntry = function(a, s) {
      return i(s);
    }) : typeof e == "function" ? (n.fromAttributes = function() {
      throw new Error("graphology-utils/getters/createNodeValueGetter: irrelevant usage.");
    }, n.fromGraph = function(a, s) {
      return r(e(s, a.getNodeAttributes(s)));
    }, n.fromEntry = function(a, s) {
      return r(e(a, s));
    }) : (n.fromAttributes = o, n.fromGraph = o, n.fromEntry = o), n;
  }
  function zg(e, t) {
    var n = {}, r = function(a) {
      return typeof a > "u" ? t : a;
    };
    typeof t == "function" && (r = t);
    var i = function(a) {
      return r(a[e]);
    }, o = function() {
      return r(void 0);
    };
    return typeof e == "string" ? (n.fromAttributes = i, n.fromGraph = function(a, s) {
      return i(a.getEdgeAttributes(s));
    }, n.fromEntry = function(a, s) {
      return i(s);
    }, n.fromPartialEntry = n.fromEntry, n.fromMinimalEntry = n.fromEntry) : typeof e == "function" ? (n.fromAttributes = function() {
      throw new Error("graphology-utils/getters/createEdgeValueGetter: irrelevant usage.");
    }, n.fromGraph = function(a, s) {
      var l = a.extremities(s);
      return r(e(s, a.getEdgeAttributes(s), l[0], l[1], a.getNodeAttributes(l[0]), a.getNodeAttributes(l[1]), a.isUndirected(s)));
    }, n.fromEntry = function(a, s, l, c, h, f, p) {
      return r(e(a, s, l, c, h, f, p));
    }, n.fromPartialEntry = function(a, s, l, c) {
      return r(e(a, s, l, c));
    }, n.fromMinimalEntry = function(a, s) {
      return r(e(a, s));
    }) : (n.fromAttributes = o, n.fromGraph = o, n.fromEntry = o, n.fromMinimalEntry = o), n;
  }
  Po.createNodeValueGetter = y1;
  Po.createEdgeValueGetter = zg;
  Po.createEdgeWeightGetter = function(e) {
    return zg(e, v1);
  };
  var Qn = {}, Co = 10, hf = 3;
  Qn.assign = function(e) {
    e = e || {};
    var t = Array.prototype.slice.call(arguments).slice(1), n, r, i;
    for (n = 0, i = t.length; n < i; n++) if (t[n]) for (r in t[n]) e[r] = t[n][r];
    return e;
  };
  Qn.validateSettings = function(e) {
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
  Qn.graphToByteArrays = function(e, t) {
    var n = e.order, r = e.size, i = {}, o, a = new Float32Array(n * Co), s = new Float32Array(r * hf);
    return o = 0, e.forEachNode(function(l, c) {
      i[l] = o, a[o] = c.x, a[o + 1] = c.y, a[o + 2] = 0, a[o + 3] = 0, a[o + 4] = 0, a[o + 5] = 0, a[o + 6] = 1, a[o + 7] = 1, a[o + 8] = c.size || 1, a[o + 9] = c.fixed ? 1 : 0, o += Co;
    }), o = 0, e.forEachEdge(function(l, c, h, f, p, y, k) {
      var b = i[h], I = i[f], S = t(l, c, h, f, p, y, k);
      a[b + 6] += S, a[I + 6] += S, s[o] = b, s[o + 1] = I, s[o + 2] = S, o += hf;
    }), {
      nodes: a,
      edges: s
    };
  };
  Qn.assignLayoutChanges = function(e, t, n) {
    var r = 0;
    e.updateEachNodeAttributes(function(i, o) {
      return o.x = t[r], o.y = t[r + 1], r += Co, n ? n(i, o) : o;
    });
  };
  Qn.readGraphPositions = function(e, t) {
    var n = 0;
    e.forEachNode(function(r, i) {
      t[n] = i.x, t[n + 1] = i.y, n += Co;
    });
  };
  Qn.collectLayoutChanges = function(e, t, n) {
    for (var r = e.nodes(), i = {}, o = 0, a = 0, s = t.length; o < s; o += Co) {
      if (n) {
        var l = Object.assign({}, e.getNodeAttributes(r[a]));
        l.x = t[o], l.y = t[o + 1], l = n(r[a], l), i[r[a]] = {
          x: l.x,
          y: l.y
        };
      } else i[r[a]] = {
        x: t[o],
        y: t[o + 1]
      };
      a++;
    }
    return i;
  };
  Qn.createWorker = function(t) {
    var n = window.URL || window.webkitURL, r = t.toString(), i = n.createObjectURL(new Blob([
      "(" + r + ").call(this);"
    ], {
      type: "text/javascript"
    })), o = new Worker(i);
    return n.revokeObjectURL(i), o;
  };
  var Og = {
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
  }, w1 = m1, E1 = Ss, S1 = Po.createEdgeWeightGetter, vi = Qn, _1 = Og;
  function Er(e, t) {
    if (t = t || {}, !E1(e)) throw new Error("graphology-layout-forceatlas2/worker: the given graph is not a valid graphology instance.");
    var n = S1("getEdgeWeight" in t ? t.getEdgeWeight : "weight").fromEntry, r = vi.assign({}, _1, t.settings), i = vi.validateSettings(r);
    if (i) throw new Error("graphology-layout-forceatlas2/worker: " + i.message);
    this.worker = null, this.graph = e, this.settings = r, this.getEdgeWeight = n, this.matrices = null, this.running = false, this.killed = false, this.outputReducer = typeof t.outputReducer == "function" ? t.outputReducer : null, this.handleMessage = this.handleMessage.bind(this);
    var o = void 0, a = this;
    this.handleGraphUpdate = function() {
      a.worker && a.worker.terminate(), o && clearTimeout(o), o = setTimeout(function() {
        o = void 0, a.spawnWorker();
      }, 0);
    }, e.on("nodeAdded", this.handleGraphUpdate), e.on("edgeAdded", this.handleGraphUpdate), e.on("nodeDropped", this.handleGraphUpdate), e.on("edgeDropped", this.handleGraphUpdate), this.spawnWorker();
  }
  Er.prototype.isRunning = function() {
    return this.running;
  };
  Er.prototype.spawnWorker = function() {
    this.worker && this.worker.terminate(), this.worker = vi.createWorker(w1), this.worker.addEventListener("message", this.handleMessage), this.running && (this.running = false, this.start());
  };
  Er.prototype.handleMessage = function(e) {
    if (this.running) {
      var t = new Float32Array(e.data.nodes);
      vi.assignLayoutChanges(this.graph, t, this.outputReducer), this.outputReducer && vi.readGraphPositions(this.graph, t), this.matrices.nodes = t, this.askForIterations();
    }
  };
  Er.prototype.askForIterations = function(e) {
    var t = this.matrices, n = {
      settings: this.settings,
      nodes: t.nodes.buffer
    }, r = [
      t.nodes.buffer
    ];
    return e && (n.edges = t.edges.buffer, r.push(t.edges.buffer)), this.worker.postMessage(n, r), this;
  };
  Er.prototype.start = function() {
    if (this.killed) throw new Error("graphology-layout-forceatlas2/worker.start: layout was killed.");
    return this.running ? this : (this.matrices = vi.graphToByteArrays(this.graph, this.getEdgeWeight), this.running = true, this.askForIterations(true), this);
  };
  Er.prototype.stop = function() {
    return this.running = false, this;
  };
  Er.prototype.kill = function() {
    if (this.killed) return this;
    this.running = false, this.killed = true, this.matrices = null, this.worker.terminate(), this.graph.removeListener("nodeAdded", this.handleGraphUpdate), this.graph.removeListener("edgeAdded", this.handleGraphUpdate), this.graph.removeListener("nodeDropped", this.handleGraphUpdate), this.graph.removeListener("edgeDropped", this.handleGraphUpdate);
  };
  var k1 = Er;
  const b1 = xo(k1);
  var qe = 0, Be = 1, Te = 2, Re = 3, In = 4, Fn = 5, Ae = 6, pf = 7, oa = 8, gf = 9, C1 = 0, x1 = 1, T1 = 2, ut = 0, Xt = 1, Rt = 2, _r = 3, Jn = 4, Ke = 5, zt = 6, bn = 7, Cn = 8, mf = 3, hn = 10, R1 = 3, kt = 9, cl = 10, A1 = function(t, n, r) {
    var i, o, a, s, l, c, h, f, p, y, k = n.length, b = r.length, I = t.adjustSizes, S = t.barnesHutTheta * t.barnesHutTheta, m, v, E, A, F, R, L, x = [];
    for (a = 0; a < k; a += hn) n[a + In] = n[a + Te], n[a + Fn] = n[a + Re], n[a + Te] = 0, n[a + Re] = 0;
    if (t.outboundAttractionDistribution) {
      for (m = 0, a = 0; a < k; a += hn) m += n[a + Ae];
      m /= k / hn;
    }
    if (t.barnesHutOptimize) {
      var G = 1 / 0, V = -1 / 0, B = 1 / 0, W = -1 / 0, O, re, fe;
      for (a = 0; a < k; a += hn) G = Math.min(G, n[a + qe]), V = Math.max(V, n[a + qe]), B = Math.min(B, n[a + Be]), W = Math.max(W, n[a + Be]);
      var te = V - G, _ = W - B;
      for (te > _ ? (B -= (te - _) / 2, W = B + te) : (G -= (_ - te) / 2, V = G + _), x[0 + ut] = -1, x[0 + Xt] = (G + V) / 2, x[0 + Rt] = (B + W) / 2, x[0 + _r] = Math.max(V - G, W - B), x[0 + Jn] = -1, x[0 + Ke] = -1, x[0 + zt] = 0, x[0 + bn] = 0, x[0 + Cn] = 0, i = 1, a = 0; a < k; a += hn) for (o = 0, fe = mf; ; ) if (x[o + Ke] >= 0) {
        n[a + qe] < x[o + Xt] ? n[a + Be] < x[o + Rt] ? O = x[o + Ke] : O = x[o + Ke] + kt : n[a + Be] < x[o + Rt] ? O = x[o + Ke] + kt * 2 : O = x[o + Ke] + kt * 3, x[o + bn] = (x[o + bn] * x[o + zt] + n[a + qe] * n[a + Ae]) / (x[o + zt] + n[a + Ae]), x[o + Cn] = (x[o + Cn] * x[o + zt] + n[a + Be] * n[a + Ae]) / (x[o + zt] + n[a + Ae]), x[o + zt] += n[a + Ae], o = O;
        continue;
      } else if (x[o + ut] < 0) {
        x[o + ut] = a;
        break;
      } else {
        if (x[o + Ke] = i * kt, f = x[o + _r] / 2, p = x[o + Ke], x[p + ut] = -1, x[p + Xt] = x[o + Xt] - f, x[p + Rt] = x[o + Rt] - f, x[p + _r] = f, x[p + Jn] = p + kt, x[p + Ke] = -1, x[p + zt] = 0, x[p + bn] = 0, x[p + Cn] = 0, p += kt, x[p + ut] = -1, x[p + Xt] = x[o + Xt] - f, x[p + Rt] = x[o + Rt] + f, x[p + _r] = f, x[p + Jn] = p + kt, x[p + Ke] = -1, x[p + zt] = 0, x[p + bn] = 0, x[p + Cn] = 0, p += kt, x[p + ut] = -1, x[p + Xt] = x[o + Xt] + f, x[p + Rt] = x[o + Rt] - f, x[p + _r] = f, x[p + Jn] = p + kt, x[p + Ke] = -1, x[p + zt] = 0, x[p + bn] = 0, x[p + Cn] = 0, p += kt, x[p + ut] = -1, x[p + Xt] = x[o + Xt] + f, x[p + Rt] = x[o + Rt] + f, x[p + _r] = f, x[p + Jn] = x[o + Jn], x[p + Ke] = -1, x[p + zt] = 0, x[p + bn] = 0, x[p + Cn] = 0, i += 4, n[x[o + ut] + qe] < x[o + Xt] ? n[x[o + ut] + Be] < x[o + Rt] ? O = x[o + Ke] : O = x[o + Ke] + kt : n[x[o + ut] + Be] < x[o + Rt] ? O = x[o + Ke] + kt * 2 : O = x[o + Ke] + kt * 3, x[o + zt] = n[x[o + ut] + Ae], x[o + bn] = n[x[o + ut] + qe], x[o + Cn] = n[x[o + ut] + Be], x[O + ut] = x[o + ut], x[o + ut] = -1, n[a + qe] < x[o + Xt] ? n[a + Be] < x[o + Rt] ? re = x[o + Ke] : re = x[o + Ke] + kt : n[a + Be] < x[o + Rt] ? re = x[o + Ke] + kt * 2 : re = x[o + Ke] + kt * 3, O === re) if (fe--) {
          o = O;
          continue;
        } else {
          fe = mf;
          break;
        }
        x[re + ut] = a;
        break;
      }
    }
    if (t.barnesHutOptimize) for (v = t.scalingRatio, a = 0; a < k; a += hn) for (o = 0; ; ) if (x[o + Ke] >= 0) if (R = Math.pow(n[a + qe] - x[o + bn], 2) + Math.pow(n[a + Be] - x[o + Cn], 2), y = x[o + _r], 4 * y * y / R < S) {
      if (E = n[a + qe] - x[o + bn], A = n[a + Be] - x[o + Cn], I === true ? R > 0 ? (L = v * n[a + Ae] * x[o + zt] / R, n[a + Te] += E * L, n[a + Re] += A * L) : R < 0 && (L = -v * n[a + Ae] * x[o + zt] / Math.sqrt(R), n[a + Te] += E * L, n[a + Re] += A * L) : R > 0 && (L = v * n[a + Ae] * x[o + zt] / R, n[a + Te] += E * L, n[a + Re] += A * L), o = x[o + Jn], o < 0) break;
      continue;
    } else {
      o = x[o + Ke];
      continue;
    }
    else {
      if (c = x[o + ut], c >= 0 && c !== a && (E = n[a + qe] - n[c + qe], A = n[a + Be] - n[c + Be], R = E * E + A * A, I === true ? R > 0 ? (L = v * n[a + Ae] * n[c + Ae] / R, n[a + Te] += E * L, n[a + Re] += A * L) : R < 0 && (L = -v * n[a + Ae] * n[c + Ae] / Math.sqrt(R), n[a + Te] += E * L, n[a + Re] += A * L) : R > 0 && (L = v * n[a + Ae] * n[c + Ae] / R, n[a + Te] += E * L, n[a + Re] += A * L)), o = x[o + Jn], o < 0) break;
      continue;
    }
    else for (v = t.scalingRatio, s = 0; s < k; s += hn) for (l = 0; l < s; l += hn) E = n[s + qe] - n[l + qe], A = n[s + Be] - n[l + Be], I === true ? (R = Math.sqrt(E * E + A * A) - n[s + oa] - n[l + oa], R > 0 ? (L = v * n[s + Ae] * n[l + Ae] / R / R, n[s + Te] += E * L, n[s + Re] += A * L, n[l + Te] -= E * L, n[l + Re] -= A * L) : R < 0 && (L = 100 * v * n[s + Ae] * n[l + Ae], n[s + Te] += E * L, n[s + Re] += A * L, n[l + Te] -= E * L, n[l + Re] -= A * L)) : (R = Math.sqrt(E * E + A * A), R > 0 && (L = v * n[s + Ae] * n[l + Ae] / R / R, n[s + Te] += E * L, n[s + Re] += A * L, n[l + Te] -= E * L, n[l + Re] -= A * L));
    for (p = t.gravity / t.scalingRatio, v = t.scalingRatio, a = 0; a < k; a += hn) L = 0, E = n[a + qe], A = n[a + Be], R = Math.sqrt(Math.pow(E, 2) + Math.pow(A, 2)), t.strongGravityMode ? R > 0 && (L = v * n[a + Ae] * p) : R > 0 && (L = v * n[a + Ae] * p / R), n[a + Te] -= E * L, n[a + Re] -= A * L;
    for (v = 1 * (t.outboundAttractionDistribution ? m : 1), h = 0; h < b; h += R1) s = r[h + C1], l = r[h + x1], f = r[h + T1], F = Math.pow(f, t.edgeWeightInfluence), E = n[s + qe] - n[l + qe], A = n[s + Be] - n[l + Be], I === true ? (R = Math.sqrt(E * E + A * A) - n[s + oa] - n[l + oa], t.linLogMode ? t.outboundAttractionDistribution ? R > 0 && (L = -v * F * Math.log(1 + R) / R / n[s + Ae]) : R > 0 && (L = -v * F * Math.log(1 + R) / R) : t.outboundAttractionDistribution ? R > 0 && (L = -v * F / n[s + Ae]) : R > 0 && (L = -v * F)) : (R = Math.sqrt(Math.pow(E, 2) + Math.pow(A, 2)), t.linLogMode ? t.outboundAttractionDistribution ? R > 0 && (L = -v * F * Math.log(1 + R) / R / n[s + Ae]) : R > 0 && (L = -v * F * Math.log(1 + R) / R) : t.outboundAttractionDistribution ? (R = 1, L = -v * F / n[s + Ae]) : (R = 1, L = -v * F)), R > 0 && (n[s + Te] += E * L, n[s + Re] += A * L, n[l + Te] -= E * L, n[l + Re] -= A * L);
    var $, H, D, C, Y, ie;
    if (I === true) for (a = 0; a < k; a += hn) n[a + gf] !== 1 && ($ = Math.sqrt(Math.pow(n[a + Te], 2) + Math.pow(n[a + Re], 2)), $ > cl && (n[a + Te] = n[a + Te] * cl / $, n[a + Re] = n[a + Re] * cl / $), H = n[a + Ae] * Math.sqrt((n[a + In] - n[a + Te]) * (n[a + In] - n[a + Te]) + (n[a + Fn] - n[a + Re]) * (n[a + Fn] - n[a + Re])), D = Math.sqrt((n[a + In] + n[a + Te]) * (n[a + In] + n[a + Te]) + (n[a + Fn] + n[a + Re]) * (n[a + Fn] + n[a + Re])) / 2, C = 0.1 * Math.log(1 + D) / (1 + Math.sqrt(H)), Y = n[a + qe] + n[a + Te] * (C / t.slowDown), n[a + qe] = Y, ie = n[a + Be] + n[a + Re] * (C / t.slowDown), n[a + Be] = ie);
    else for (a = 0; a < k; a += hn) n[a + gf] !== 1 && (H = n[a + Ae] * Math.sqrt((n[a + In] - n[a + Te]) * (n[a + In] - n[a + Te]) + (n[a + Fn] - n[a + Re]) * (n[a + Fn] - n[a + Re])), D = Math.sqrt((n[a + In] + n[a + Te]) * (n[a + In] + n[a + Te]) + (n[a + Fn] + n[a + Re]) * (n[a + Fn] + n[a + Re])) / 2, C = n[a + pf] * Math.log(1 + D) / (1 + Math.sqrt(H)), n[a + pf] = Math.min(1, Math.sqrt(C * (Math.pow(n[a + Te], 2) + Math.pow(n[a + Re], 2)) / (1 + Math.sqrt(H)))), Y = n[a + qe] + n[a + Te] * (C / t.slowDown), n[a + qe] = Y, ie = n[a + Be] + n[a + Re] * (C / t.slowDown), n[a + Be] = ie);
    return {};
  }, L1 = Ss, D1 = Po.createEdgeWeightGetter, P1 = A1, $i = Qn, I1 = Og;
  function Gg(e, t, n) {
    if (!L1(t)) throw new Error("graphology-layout-forceatlas2: the given graph is not a valid graphology instance.");
    typeof n == "number" && (n = {
      iterations: n
    });
    var r = n.iterations;
    if (typeof r != "number") throw new Error("graphology-layout-forceatlas2: invalid number of iterations.");
    if (r <= 0) throw new Error("graphology-layout-forceatlas2: you should provide a positive number of iterations.");
    var i = D1("getEdgeWeight" in n ? n.getEdgeWeight : "weight").fromEntry, o = typeof n.outputReducer == "function" ? n.outputReducer : null, a = $i.assign({}, I1, n.settings), s = $i.validateSettings(a);
    if (s) throw new Error("graphology-layout-forceatlas2: " + s.message);
    var l = $i.graphToByteArrays(t, i), c;
    for (c = 0; c < r; c++) P1(a, l.nodes, l.edges);
    if (e) {
      $i.assignLayoutChanges(t, l.nodes, o);
      return;
    }
    return $i.collectLayoutChanges(t, l.nodes);
  }
  function F1(e) {
    var t = typeof e == "number" ? e : e.order;
    return {
      barnesHutOptimize: t > 2e3,
      strongGravityMode: true,
      gravity: 0.05,
      scalingRatio: 10,
      slowDown: 1 + Math.log(t)
    };
  }
  var yc = Gg.bind(null, false);
  yc.assign = Gg.bind(null, true);
  yc.inferSettings = F1;
  var N1 = yc;
  const z1 = xo(N1);
  var ji = 0, Hi = 1, aa = 2, Wi = 3;
  function O1(e, t) {
    return e + "\xA7" + t;
  }
  function vf() {
    return 0.01 * (0.5 - Math.random());
  }
  var G1 = function(t, n) {
    var r = t.margin, i = t.ratio, o = t.expansion, a = t.gridSize, s = t.speed, l, c, h, f, p, y, k = true, b = n.length, I = b / Wi | 0, S = new Float32Array(I), m = new Float32Array(I), v = 1 / 0, E = 1 / 0, A = -1 / 0, F = -1 / 0;
    for (l = 0; l < b; l += Wi) h = n[l + ji], f = n[l + Hi], y = n[l + aa] * i + r, v = Math.min(v, h - y), A = Math.max(A, h + y), E = Math.min(E, f - y), F = Math.max(F, f + y);
    var R = A - v, L = F - E, x = (v + A) / 2, G = (E + F) / 2;
    v = x - o * R / 2, A = x + o * R / 2, E = G - o * L / 2, F = G + o * L / 2;
    var V = new Array(a * a), B = V.length, W;
    for (W = 0; W < B; W++) V[W] = [];
    var O, re, fe, te, _, $, H, D, C, Y;
    for (l = 0; l < b; l += Wi) for (h = n[l + ji], f = n[l + Hi], y = n[l + aa] * i + r, O = h - y, re = h + y, fe = f - y, te = f + y, _ = Math.floor(a * (O - v) / (A - v)), $ = Math.floor(a * (re - v) / (A - v)), H = Math.floor(a * (fe - E) / (F - E)), D = Math.floor(a * (te - E) / (F - E)), C = _; C <= $; C++) for (Y = H; Y <= D; Y++) V[C * a + Y].push(l);
    var ie, _e = /* @__PURE__ */ new Set(), Se, oe, X, Qe, ze, _n, at, mt, Xe, me, ve, he, vt;
    for (W = 0; W < B; W++) for (ie = V[W], l = 0, p = ie.length; l < p; l++) for (Se = ie[l], X = n[Se + ji], ze = n[Se + Hi], at = n[Se + aa], c = l + 1; c < p; c++) oe = ie[c], Xe = O1(Se, oe), !(B > 1 && _e.has(Xe)) && (B > 1 && _e.add(Xe), Qe = n[oe + ji], _n = n[oe + Hi], mt = n[oe + aa], me = Qe - X, ve = _n - ze, he = Math.sqrt(me * me + ve * ve), vt = he < at * i + r + (mt * i + r), vt && (k = false, oe = oe / Wi | 0, he > 0 ? (S[oe] += me / he * (1 + at), m[oe] += ve / he * (1 + at)) : (S[oe] += R * vf(), m[oe] += L * vf())));
    for (l = 0, c = 0; l < b; l += Wi, c++) n[l + ji] += S[c] * 0.1 * s, n[l + Hi] += m[c] * 0.1 * s;
    return {
      converged: k
    };
  }, Ci = {}, Xa = 3;
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
    var n = e.order, r = new Float32Array(n * Xa), i = 0;
    return e.forEachNode(function(o, a) {
      typeof t == "function" && (a = t(o, a)), r[i] = a.x, r[i + 1] = a.y, r[i + 2] = a.size || 1, i += Xa;
    }), r;
  };
  Ci.assignLayoutChanges = function(e, t, n) {
    var r = 0;
    e.forEachNode(function(i) {
      var o = {
        x: t[r],
        y: t[r + 1]
      };
      typeof n == "function" && (o = n(i, o)), e.mergeNodeAttributes(i, o), r += Xa;
    });
  };
  Ci.collectLayoutChanges = function(e, t, n) {
    var r = {}, i = 0;
    return e.forEachNode(function(o) {
      var a = {
        x: t[i],
        y: t[i + 1]
      };
      typeof n == "function" && (a = n(o, a)), r[o] = a, i += Xa;
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
  var U1 = {
    gridSize: 20,
    margin: 5,
    expansion: 1.1,
    ratio: 1,
    speed: 3
  }, B1 = Ss, M1 = G1, sa = Ci, $1 = U1, j1 = 500;
  function Ug(e, t, n) {
    if (!B1(t)) throw new Error("graphology-layout-noverlap: the given graph is not a valid graphology instance.");
    typeof n == "number" ? n = {
      maxIterations: n
    } : n = n || {};
    var r = n.maxIterations || j1;
    if (typeof r != "number" || r <= 0) throw new Error("graphology-layout-force: you should provide a positive number of maximum iterations.");
    var i = Object.assign({}, $1, n.settings), o = sa.validateSettings(i);
    if (o) throw new Error("graphology-layout-noverlap: " + o.message);
    var a = sa.graphToByteArray(t, n.inputReducer), s = false, l;
    for (l = 0; l < r && !s; l++) s = M1(i, a).converged;
    if (e) {
      sa.assignLayoutChanges(t, a, n.outputReducer);
      return;
    }
    return sa.collectLayoutChanges(t, a, n.outputReducer);
  }
  var Bg = Ug.bind(null, false);
  Bg.assign = Ug.bind(null, true);
  var H1 = Bg;
  const W1 = xo(H1);
  function V1(e, t) {
    if (typeof e != "object" || !e) return e;
    var n = e[Symbol.toPrimitive];
    if (n !== void 0) {
      var r = n.call(e, t);
      if (typeof r != "object") return r;
      throw new TypeError("@@toPrimitive must return a primitive value.");
    }
    return (t === "string" ? String : Number)(e);
  }
  function Mg(e) {
    var t = V1(e, "string");
    return typeof t == "symbol" ? t : t + "";
  }
  function $g(e, t, n) {
    return (t = Mg(t)) in e ? Object.defineProperty(e, t, {
      value: n,
      enumerable: true,
      configurable: true,
      writable: true
    }) : e[t] = n, e;
  }
  function yf(e, t) {
    var n = Object.keys(e);
    if (Object.getOwnPropertySymbols) {
      var r = Object.getOwnPropertySymbols(e);
      t && (r = r.filter(function(i) {
        return Object.getOwnPropertyDescriptor(e, i).enumerable;
      })), n.push.apply(n, r);
    }
    return n;
  }
  function Za(e) {
    for (var t = 1; t < arguments.length; t++) {
      var n = arguments[t] != null ? arguments[t] : {};
      t % 2 ? yf(Object(n), true).forEach(function(r) {
        $g(e, r, n[r]);
      }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(n)) : yf(Object(n)).forEach(function(r) {
        Object.defineProperty(e, r, Object.getOwnPropertyDescriptor(n, r));
      });
    }
    return e;
  }
  function K1(e, t) {
    if (!(e instanceof t)) throw new TypeError("Cannot call a class as a function");
  }
  function Y1(e, t) {
    for (var n = 0; n < t.length; n++) {
      var r = t[n];
      r.enumerable = r.enumerable || false, r.configurable = true, "value" in r && (r.writable = true), Object.defineProperty(e, Mg(r.key), r);
    }
  }
  function Q1(e, t, n) {
    return t && Y1(e.prototype, t), Object.defineProperty(e, "prototype", {
      writable: false
    }), e;
  }
  function qa(e) {
    return qa = Object.setPrototypeOf ? Object.getPrototypeOf.bind() : function(t) {
      return t.__proto__ || Object.getPrototypeOf(t);
    }, qa(e);
  }
  function jg() {
    try {
      var e = !Boolean.prototype.valueOf.call(Reflect.construct(Boolean, [], function() {
      }));
    } catch {
    }
    return (jg = function() {
      return !!e;
    })();
  }
  function Hg(e) {
    if (e === void 0) throw new ReferenceError("this hasn't been initialised - super() hasn't been called");
    return e;
  }
  function X1(e, t) {
    if (t && (typeof t == "object" || typeof t == "function")) return t;
    if (t !== void 0) throw new TypeError("Derived constructors may only return object or undefined");
    return Hg(e);
  }
  function Z1(e, t, n) {
    return t = qa(t), X1(e, jg() ? Reflect.construct(t, n || [], qa(e).constructor) : t.apply(e, n));
  }
  function pu(e, t) {
    return pu = Object.setPrototypeOf ? Object.setPrototypeOf.bind() : function(n, r) {
      return n.__proto__ = r, n;
    }, pu(e, t);
  }
  function q1(e, t) {
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
  function J1(e) {
    if (Array.isArray(e)) return gu(e);
  }
  function eS(e) {
    if (typeof Symbol < "u" && e[Symbol.iterator] != null || e["@@iterator"] != null) return Array.from(e);
  }
  function tS(e, t) {
    if (e) {
      if (typeof e == "string") return gu(e, t);
      var n = {}.toString.call(e).slice(8, -1);
      return n === "Object" && e.constructor && (n = e.constructor.name), n === "Map" || n === "Set" ? Array.from(e) : n === "Arguments" || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(n) ? gu(e, t) : void 0;
    }
  }
  function nS() {
    throw new TypeError(`Invalid attempt to spread non-iterable instance.
In order to be iterable, non-array objects must have a [Symbol.iterator]() method.`);
  }
  function dl(e) {
    return J1(e) || eS(e) || tS(e) || nS();
  }
  function Wg(e, t, n, r) {
    var i = Math.pow(1 - e, 2) * t.x + 2 * (1 - e) * e * n.x + Math.pow(e, 2) * r.x, o = Math.pow(1 - e, 2) * t.y + 2 * (1 - e) * e * n.y + Math.pow(e, 2) * r.y;
    return {
      x: i,
      y: o
    };
  }
  function rS(e, t, n) {
    for (var r = 20, i = 0, o = e, a = 0; a < r; a++) {
      var s = Wg((a + 1) / r, e, t, n);
      i += Math.sqrt(Math.pow(o.x - s.x, 2) + Math.pow(o.y - s.y, 2)), o = s;
    }
    return i;
  }
  function iS(e) {
    var t = e.curvatureAttribute, n = e.defaultCurvature, r = e.keepLabelUpright, i = r === void 0 ? true : r;
    return function(o, a, s, l, c) {
      var h = c.edgeLabelSize, f = a[t] || n, p = c.edgeLabelFont, y = c.edgeLabelWeight, k = c.edgeLabelColor.attribute ? a[c.edgeLabelColor.attribute] || c.edgeLabelColor.color || "#000" : c.edgeLabelColor.color, b = a.label;
      if (b) {
        o.fillStyle = k, o.font = "".concat(y, " ").concat(h, "px ").concat(p);
        var I = !i || s.x < l.x, S = I ? s.x : l.x, m = I ? s.y : l.y, v = I ? l.x : s.x, E = I ? l.y : s.y, A = (S + v) / 2, F = (m + E) / 2, R = v - S, L = E - m, x = Math.sqrt(Math.pow(R, 2) + Math.pow(L, 2)), G = I ? 1 : -1, V = A + L * f * G, B = F - R * f * G, W = a.size * 0.7 + 5, O = {
          x: B - m,
          y: -(V - S)
        }, re = Math.sqrt(Math.pow(O.x, 2) + Math.pow(O.y, 2)), fe = {
          x: E - B,
          y: -(v - V)
        }, te = Math.sqrt(Math.pow(fe.x, 2) + Math.pow(fe.y, 2));
        S += W * O.x / re, m += W * O.y / re, v += W * fe.x / te, E += W * fe.y / te, V += W * L / x, B -= W * R / x;
        var _ = {
          x: V,
          y: B
        }, $ = {
          x: S,
          y: m
        }, H = {
          x: v,
          y: E
        }, D = rS($, _, H);
        if (!(D < s.size + l.size)) {
          var C = o.measureText(b).width, Y = D - s.size - l.size;
          if (C > Y) {
            var ie = "\u2026";
            for (b = b + ie, C = o.measureText(b).width; C > Y && b.length > 1; ) b = b.slice(0, -2) + ie, C = o.measureText(b).width;
            if (b.length < 4) return;
          }
          for (var _e = {}, Se = 0, oe = b.length; Se < oe; Se++) {
            var X = b[Se];
            _e[X] || (_e[X] = o.measureText(X).width * (1 + f * 0.35));
          }
          for (var Qe = 0.5 - C / D / 2, ze = 0, _n = b.length; ze < _n; ze++) {
            var at = b[ze], mt = Wg(Qe, $, _, H), Xe = 2 * (1 - Qe) * (V - S) + 2 * Qe * (v - V), me = 2 * (1 - Qe) * (B - m) + 2 * Qe * (E - B), ve = Math.atan2(me, Xe);
            o.save(), o.translate(mt.x, mt.y), o.rotate(ve), o.fillText(at, 0, 0), o.restore(), Qe += _e[at] / D;
          }
        }
      }
    };
  }
  function oS(e) {
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
  function aS(e) {
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
  var Vg = 0.25, sS = {
    arrowHead: null,
    curvatureAttribute: "curvature",
    defaultCurvature: Vg
  }, Kg = WebGLRenderingContext, wf = Kg.UNSIGNED_BYTE, er = Kg.FLOAT;
  function wc(e) {
    var t = Za(Za({}, sS), e || {}), n = t, r = n.arrowHead, i = n.curvatureAttribute, o = n.drawLabel, a = (r == null ? void 0 : r.extremity) === "target" || (r == null ? void 0 : r.extremity) === "both", s = (r == null ? void 0 : r.extremity) === "source" || (r == null ? void 0 : r.extremity) === "both", l = [
      "u_matrix",
      "u_sizeRatio",
      "u_dimensions",
      "u_pixelRatio",
      "u_feather",
      "u_minEdgeThickness"
    ].concat(dl(r ? [
      "u_lengthToThicknessRatio",
      "u_widenessToThicknessRatio"
    ] : []));
    return function(c) {
      q1(h, c);
      function h() {
        var f;
        K1(this, h);
        for (var p = arguments.length, y = new Array(p), k = 0; k < p; k++) y[k] = arguments[k];
        return f = Z1(this, h, [].concat(y)), $g(Hg(f), "drawLabel", o || iS(t)), f;
      }
      return Q1(h, [
        {
          key: "getDefinition",
          value: function() {
            return {
              VERTICES: 6,
              VERTEX_SHADER_SOURCE: aS(t),
              FRAGMENT_SHADER_SOURCE: oS(t),
              METHOD: WebGLRenderingContext.TRIANGLES,
              UNIFORMS: l,
              ATTRIBUTES: [
                {
                  name: "a_source",
                  size: 2,
                  type: er
                },
                {
                  name: "a_target",
                  size: 2,
                  type: er
                }
              ].concat(dl(a ? [
                {
                  name: "a_targetSize",
                  size: 1,
                  type: er
                }
              ] : []), dl(s ? [
                {
                  name: "a_sourceSize",
                  size: 1,
                  type: er
                }
              ] : []), [
                {
                  name: "a_thickness",
                  size: 1,
                  type: er
                },
                {
                  name: "a_curvature",
                  size: 1,
                  type: er
                },
                {
                  name: "a_color",
                  size: 4,
                  type: wf,
                  normalized: true
                },
                {
                  name: "a_id",
                  size: 4,
                  type: wf,
                  normalized: true
                }
              ]),
              CONSTANT_ATTRIBUTES: [
                {
                  name: "a_current",
                  size: 1,
                  type: er
                },
                {
                  name: "a_direction",
                  size: 1,
                  type: er
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
            var S, m = I.size || 1, v = k.x, E = k.y, A = b.x, F = b.y, R = Si(I.color), L = (S = I[i]) !== null && S !== void 0 ? S : Vg, x = this.array;
            x[y++] = v, x[y++] = E, x[y++] = A, x[y++] = F, a && (x[y++] = b.size), s && (x[y++] = k.size), x[y++] = m, x[y++] = L, x[y++] = R, x[y++] = p;
          }
        },
        {
          key: "setUniforms",
          value: function(p, y) {
            var k = y.gl, b = y.uniformLocations, I = b.u_matrix, S = b.u_pixelRatio, m = b.u_feather, v = b.u_sizeRatio, E = b.u_dimensions, A = b.u_minEdgeThickness;
            if (k.uniformMatrix3fv(I, false, p.matrix), k.uniform1f(S, p.pixelRatio), k.uniform1f(v, p.sizeRatio), k.uniform1f(m, p.antiAliasingFeather), k.uniform2f(E, p.width * p.pixelRatio, p.height * p.pixelRatio), k.uniform1f(A, p.minEdgeThickness), r) {
              var F = b.u_lengthToThicknessRatio, R = b.u_widenessToThicknessRatio;
              k.uniform1f(F, r.lengthToThicknessRatio), k.uniform1f(R, r.widenessToThicknessRatio);
            }
          }
        }
      ]), h;
    }(vs);
  }
  var lS = wc();
  wc({
    arrowHead: ws
  });
  wc({
    arrowHead: Za(Za({}, ws), {}, {
      extremity: "both"
    })
  });
  const Yg = (e) => {
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
  }, Qg = (e, t, n) => "#" + [
    e,
    t,
    n
  ].map((r) => {
    const i = Math.max(0, Math.min(255, Math.round(r))).toString(16);
    return i.length === 1 ? "0" + i : i;
  }).join(""), fl = (e, t) => {
    const n = Yg(e), r = {
      r: 18,
      g: 18,
      b: 28
    };
    return Qg(r.r + (n.r - r.r) * t, r.g + (n.g - r.g) * t, r.b + (n.b - r.b) * t);
  }, uS = (e, t) => {
    const n = Yg(e);
    return Qg(n.r + (255 - n.r) * (t - 1) / t, n.g + (255 - n.g) * (t - 1) / t, n.b + (255 - n.b) * (t - 1) / t);
  }, cS = {
    maxIterations: 20,
    ratio: 1.1,
    margin: 10,
    expansion: 1.05
  }, dS = (e) => {
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
  }, fS = (e = {}) => {
    const t = N.useRef(null), n = N.useRef(null), r = N.useRef(null), i = N.useRef(null), o = N.useRef(null), a = N.useRef(/* @__PURE__ */ new Set()), s = N.useRef(/* @__PURE__ */ new Set()), l = N.useRef(/* @__PURE__ */ new Map()), c = N.useRef(null), h = N.useRef(null), f = N.useRef(null), [p, y] = N.useState(false), [k, b] = N.useState(null);
    N.useEffect(() => {
      var _a2;
      a.current = e.highlightedNodeIds || /* @__PURE__ */ new Set(), s.current = e.blastRadiusNodeIds || /* @__PURE__ */ new Set(), l.current = e.animatedNodes || /* @__PURE__ */ new Map(), c.current = e.visibleEdgeTypes || null, (_a2 = n.current) == null ? void 0 : _a2.refresh();
    }, [
      e.highlightedNodeIds,
      e.blastRadiusNodeIds,
      e.animatedNodes,
      e.visibleEdgeTypes
    ]), N.useEffect(() => {
      if (!e.animatedNodes || e.animatedNodes.size === 0) {
        f.current && (cancelAnimationFrame(f.current), f.current = null);
        return;
      }
      const G = () => {
        var _a2;
        (_a2 = n.current) == null ? void 0 : _a2.refresh(), f.current = requestAnimationFrame(G);
      };
      return G(), () => {
        f.current && (cancelAnimationFrame(f.current), f.current = null);
      };
    }, [
      e.animatedNodes
    ]);
    const I = N.useCallback((G) => {
      o.current = G, b(G);
      const V = n.current;
      if (!V) return;
      const B = V.getCamera(), W = B.ratio;
      B.animate({
        ratio: W * 1.0001
      }, {
        duration: 50
      }), V.refresh();
    }, []);
    N.useEffect(() => {
      if (!t.current) return;
      const G = new Ie();
      r.current = G;
      const V = new cE(G, t.current, {
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
          curved: lS
        },
        defaultDrawNodeHover: (B, W, O) => {
          const re = W.label;
          if (!re) return;
          const fe = O.labelSize || 11, te = O.labelFont || "JetBrains Mono, monospace", _ = O.labelWeight || "500";
          B.font = `${_} ${fe}px ${te}`;
          const $ = B.measureText(re).width, H = W.size || 8, D = W.x, C = W.y - H - 10, Y = 8, _e = fe + 5 * 2, Se = $ + Y * 2, oe = 4;
          B.fillStyle = "#12121c", B.beginPath(), B.roundRect(D - Se / 2, C - _e / 2, Se, _e, oe), B.fill(), B.strokeStyle = W.color || "#6366f1", B.lineWidth = 2, B.stroke(), B.fillStyle = "#f5f5f7", B.textAlign = "center", B.textBaseline = "middle", B.fillText(re, D, C), B.beginPath(), B.arc(W.x, W.y, H + 4, 0, Math.PI * 2), B.strokeStyle = W.color || "#6366f1", B.lineWidth = 2, B.globalAlpha = 0.5, B.stroke(), B.globalAlpha = 1;
        },
        minCameraRatio: 2e-3,
        maxCameraRatio: 50,
        hideEdgesOnMove: true,
        zIndex: true,
        nodeReducer: (B, W) => {
          const O = {
            ...W
          };
          if (W.hidden) return O.hidden = true, O;
          const re = o.current, fe = a.current, te = s.current, _ = l.current, $ = fe.size > 0, H = te.size > 0, D = fe.has(B), C = te.has(B), Y = _.get(B);
          if (Y) {
            const _e = Date.now() - Y.startTime, Se = Math.min(_e / Y.duration, 1), oe = (Math.sin(Se * Math.PI * 4) + 1) / 2;
            if (Y.type === "pulse") {
              const X = 1.5 + oe * 0.8;
              O.size = (W.size || 8) * X, O.color = oe > 0.5 ? "#06b6d4" : uS("#06b6d4", 1.3), O.zIndex = 5, O.highlighted = true;
            } else if (Y.type === "ripple") {
              const X = 1.3 + oe * 1.2;
              O.size = (W.size || 8) * X, O.color = oe > 0.5 ? "#ef4444" : "#f87171", O.zIndex = 5, O.highlighted = true;
            } else if (Y.type === "glow") {
              const X = 1.4 + oe * 0.6;
              O.size = (W.size || 8) * X, O.color = oe > 0.5 ? "#a855f7" : "#c084fc", O.zIndex = 5, O.highlighted = true;
            }
            return O;
          }
          if (H && !re) return C ? (O.color = "#ef4444", O.size = (W.size || 8) * 1.8, O.zIndex = 3, O.highlighted = true) : D ? (O.color = "#06b6d4", O.size = (W.size || 8) * 1.4, O.zIndex = 2, O.highlighted = true) : (O.color = fl(W.color, 0.15), O.size = (W.size || 8) * 0.4, O.zIndex = 0), O;
          if ($ && !re) return D ? (O.color = "#06b6d4", O.size = (W.size || 8) * 1.6, O.zIndex = 2, O.highlighted = true) : (O.color = fl(W.color, 0.2), O.size = (W.size || 8) * 0.5, O.zIndex = 0), O;
          if (re) {
            const ie = r.current;
            if (ie) {
              const _e = B === re, Se = ie.hasEdge(B, re) || ie.hasEdge(re, B);
              _e ? (O.color = W.color, O.size = (W.size || 8) * 1.8, O.zIndex = 2, O.highlighted = true) : Se ? (O.color = W.color, O.size = (W.size || 8) * 1.3, O.zIndex = 1) : (O.color = fl(W.color, 0.25), O.size = (W.size || 8) * 0.6, O.zIndex = 0);
            }
          }
          return O;
        },
        edgeReducer: (B, W) => ({
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
    const S = N.useCallback((G) => {
      const V = G.order;
      if (V === 0) return;
      i.current && (i.current.kill(), i.current = null), h.current && (clearTimeout(h.current), h.current = null);
      const B = z1.inferSettings(G), W = dS(V), O = {
        ...B,
        ...W
      }, re = new b1(G, {
        settings: O
      });
      i.current = re, re.start(), y(true);
    }, []), m = N.useCallback((G) => {
      const V = n.current;
      V && (i.current && (i.current.kill(), i.current = null), h.current && (clearTimeout(h.current), h.current = null), r.current = G, V.setGraph(G), I(null), S(G), V.getCamera().animatedReset({
        duration: 500
      }));
    }, [
      S,
      I
    ]), v = N.useCallback((G) => {
      const V = n.current, B = r.current;
      if (!V || !B || !B.hasNode(G)) return;
      const W = o.current === G;
      if (o.current = G, b(G), !W) {
        const O = B.getNodeAttributes(G);
        V.getCamera().animate({
          x: O.x,
          y: O.y,
          ratio: 0.15
        }, {
          duration: 400
        });
      }
      V.refresh();
    }, []), E = N.useCallback(() => {
      var _a2;
      (_a2 = n.current) == null ? void 0 : _a2.getCamera().animatedZoom({
        duration: 200
      });
    }, []), A = N.useCallback(() => {
      var _a2;
      (_a2 = n.current) == null ? void 0 : _a2.getCamera().animatedUnzoom({
        duration: 200
      });
    }, []), F = N.useCallback(() => {
      var _a2;
      (_a2 = n.current) == null ? void 0 : _a2.getCamera().animatedReset({
        duration: 300
      }), I(null);
    }, [
      I
    ]), R = N.useCallback(() => {
      const G = r.current;
      !G || G.order === 0 || S(G);
    }, [
      S
    ]), L = N.useCallback(() => {
      var _a2;
      if (h.current && (clearTimeout(h.current), h.current = null), i.current) {
        i.current.stop(), i.current = null;
        const G = r.current;
        G && (W1.assign(G, cS), (_a2 = n.current) == null ? void 0 : _a2.refresh()), y(false);
      }
    }, []), x = N.useCallback(() => {
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
      refreshHighlights: x
    };
  }, Ef = (e, t) => t > 5e4 ? Math.max(1, e * 0.4) : t > 2e4 ? Math.max(1.5, e * 0.5) : t > 5e3 ? Math.max(2, e * 0.65) : t > 1e3 ? Math.max(2.5, e * 0.8) : e, Sf = (e, t) => {
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
  }, hS = (e, t) => {
    const n = new Ie(), r = e.nodes.length, i = /* @__PURE__ */ new Map(), o = /* @__PURE__ */ new Map(), a = /* @__PURE__ */ new Set([
      "CONTAINS",
      "DEFINES",
      "IMPORTS"
    ]);
    e.relationships.forEach((E) => {
      a.has(E.type) && (i.has(E.sourceId) || i.set(E.sourceId, []), i.get(E.sourceId).push(E.targetId), o.set(E.targetId, E.sourceId));
    });
    const s = new Map(e.nodes.map((E) => [
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
      E.forEach((x) => {
        const G = L * R, V = F * Math.sqrt((L + 1) / A);
        p.set(x, {
          x: V * Math.cos(G),
          y: V * Math.sin(G)
        }), L++;
      });
    }
    const y = Math.sqrt(r) * 1.5, k = /* @__PURE__ */ new Map();
    c.forEach((E, A) => {
      const F = Math.PI * (3 - Math.sqrt(5)), R = A * F, L = h * Math.sqrt((A + 1) / Math.max(c.length, 1)), x = h * 0.15, G = L * Math.cos(R) + (Math.random() - 0.5) * x, V = L * Math.sin(R) + (Math.random() - 0.5) * x;
      k.set(E.id, {
        x: G,
        y: V
      });
      const B = Nd[E.label] || 8, W = Ef(B, r);
      n.addNode(E.id, {
        x: G,
        y: V,
        size: W,
        color: Fd[E.label] || "#9ca3af",
        label: E.properties.name,
        nodeType: E.label,
        filePath: E.properties.filePath,
        startLine: E.properties.startLine,
        endLine: E.properties.endLine,
        hidden: false,
        mass: Sf(E.label, r)
      });
    });
    const b = (E) => {
      if (n.hasNode(E)) return;
      const A = s.get(E);
      if (!A) return;
      let F, R;
      const L = t == null ? void 0 : t.get(E), x = /* @__PURE__ */ new Set([
        "Function",
        "Class",
        "Method",
        "Interface"
      ]), G = L !== void 0 ? p.get(L) : null;
      if (G && x.has(A.label)) F = G.x + (Math.random() - 0.5) * y, R = G.y + (Math.random() - 0.5) * y;
      else {
        const fe = o.get(E), te = fe ? k.get(fe) : null;
        te ? (F = te.x + (Math.random() - 0.5) * f, R = te.y + (Math.random() - 0.5) * f) : (F = (Math.random() - 0.5) * h * 0.5, R = (Math.random() - 0.5) * h * 0.5);
      }
      k.set(E, {
        x: F,
        y: R
      });
      const V = Nd[A.label] || 8, B = Ef(V, r), W = L !== void 0, re = W && x.has(A.label) ? Od(L) : Fd[A.label] || "#9ca3af";
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
        mass: Sf(A.label, r),
        community: L,
        communityColor: W ? Od(L) : void 0
      });
    }, I = [
      ...c.map((E) => E.id)
    ], S = new Set(I);
    for (; I.length > 0; ) {
      const E = I.shift(), A = i.get(E) || [];
      for (const F of A) S.has(F) || (S.add(F), b(F), I.push(F));
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
  }, _f = (e, t) => {
    e.forEachNode((n, r) => {
      const i = t.includes(r.nodeType);
      e.setNodeAttribute(n, "hidden", !i);
    });
  }, pS = (e, t, n) => {
    const r = /* @__PURE__ */ new Set(), i = [
      {
        nodeId: t,
        depth: 0
      }
    ];
    for (; i.length > 0; ) {
      const { nodeId: o, depth: a } = i.shift();
      r.has(o) || (r.add(o), a < n && e.forEachNeighbor(o, (s) => {
        r.has(s) || i.push({
          nodeId: s,
          depth: a + 1
        });
      }));
    }
    return r;
  }, gS = (e, t, n, r) => {
    if (n === null) {
      _f(e, r);
      return;
    }
    if (t === null || !e.hasNode(t)) {
      _f(e, r);
      return;
    }
    const i = pS(e, t, n);
    e.forEachNode((o, a) => {
      const s = r.includes(a.nodeType), l = i.has(o);
      e.setNodeAttribute(o, "hidden", !s || !l);
    });
  }, Xg = N.forwardRef(({ background: e = "dark" }, t) => {
    const { graph: n, setSelectedNode: r, selectedNode: i, visibleLabels: o, visibleEdgeTypes: a, openCodePanel: s, depthFilter: l, highlightedNodeIds: c, setHighlightedNodeIds: h, aiCitationHighlightedNodeIds: f, aiToolHighlightedNodeIds: p, blastRadiusNodeIds: y, isAIHighlightsEnabled: k, toggleAIHighlights: b, animatedNodes: I } = Kp(), [S, m] = N.useState(null), v = e === "light", E = N.useMemo(() => {
      if (!k) return c;
      const $ = new Set(c);
      for (const H of f) $.add(H);
      for (const H of p) $.add(H);
      return $;
    }, [
      c,
      f,
      p,
      k
    ]), A = N.useMemo(() => k ? y : /* @__PURE__ */ new Set(), [
      y,
      k
    ]), F = N.useMemo(() => k ? I : /* @__PURE__ */ new Map(), [
      I,
      k
    ]), R = N.useCallback(($) => {
      if (!n) return;
      const H = n.nodes.find((D) => D.id === $);
      H && (r(H), s());
    }, [
      n,
      r,
      s
    ]), L = N.useCallback(($) => {
      if (!$ || !n) {
        m(null);
        return;
      }
      const H = n.nodes.find((D) => D.id === $);
      H && m(H.properties.name);
    }, [
      n
    ]), x = N.useCallback(() => {
      r(null);
    }, [
      r
    ]), { containerRef: G, sigmaRef: V, setGraph: B, resetZoom: W, focusNode: O, selectedNode: re, setSelectedNode: fe } = fS({
      onNodeClick: R,
      onNodeHover: L,
      onStageClick: x,
      highlightedNodeIds: E,
      blastRadiusNodeIds: A,
      animatedNodes: F,
      visibleEdgeTypes: a
    });
    N.useImperativeHandle(t, () => ({
      focusNode: ($) => {
        if (n) {
          const H = n.nodes.find((D) => D.id === $);
          H && (r(H), s());
        }
        O($);
      }
    }), [
      O,
      n,
      r,
      s
    ]), N.useEffect(() => {
      if (!n) return;
      const $ = /* @__PURE__ */ new Map();
      n.relationships.forEach((D) => {
        if (D.type === "MEMBER_OF" && n.nodes.find((Y) => Y.id === D.targetId && Y.label === "Community")) {
          const Y = parseInt(D.targetId.replace("comm_", ""), 10) || 0;
          $.set(D.sourceId, Y);
        }
      });
      const H = hS(n, $);
      B(H);
    }, [
      n,
      B
    ]), N.useEffect(() => {
      const $ = V.current;
      if (!$) return;
      const H = $.getGraph();
      H.order !== 0 && (gS(H, (i == null ? void 0 : i.id) || null, l, o), $.refresh());
    }, [
      o,
      l,
      i,
      V
    ]), N.useEffect(() => {
      fe(i ? i.id : null);
    }, [
      i,
      fe
    ]);
    const te = N.useCallback(() => {
      i && O(i.id);
    }, [
      i,
      O
    ]), _ = N.useCallback(() => {
      r(null), fe(null), W();
    }, [
      r,
      fe,
      W
    ]);
    return q.jsxs("div", {
      className: `relative w-full h-full ${v ? "bg-white" : "bg-void"}`,
      children: [
        q.jsx("div", {
          className: "absolute inset-0 pointer-events-none",
          children: q.jsx("div", {
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
        q.jsx("div", {
          ref: G,
          className: "sigma-container w-full h-full cursor-grab active:cursor-grabbing"
        }),
        S && !re && q.jsx("div", {
          className: "absolute top-4 left-1/2 -translate-x-1/2 px-3 py-1.5 bg-elevated/95 border border-border-subtle rounded-lg backdrop-blur-sm z-20 pointer-events-none animate-fade-in",
          children: q.jsx("span", {
            className: "font-mono text-sm text-text-primary",
            children: S
          })
        }),
        re && i && q.jsxs("div", {
          className: "absolute top-4 left-1/2 -translate-x-1/2 flex items-center gap-2 px-4 py-2 bg-accent/20 border border-accent/30 rounded-xl backdrop-blur-sm z-20 animate-slide-up",
          children: [
            q.jsx("div", {
              className: "w-2 h-2 bg-accent rounded-full animate-pulse"
            }),
            q.jsx("span", {
              className: "font-mono text-sm text-text-primary",
              children: i.properties.name
            }),
            q.jsxs("span", {
              className: "text-xs text-text-muted",
              children: [
                "(",
                i.label,
                ")"
              ]
            }),
            q.jsx("button", {
              onClick: _,
              className: "ml-2 px-2 py-0.5 text-xs text-text-secondary hover:text-text-primary hover:bg-white/10 rounded transition-colors",
              children: "Clear"
            })
          ]
        }),
        q.jsxs("div", {
          className: "absolute bottom-4 right-4 flex flex-col gap-1 z-10",
          children: [
            q.jsx("div", {
              className: "h-px bg-border-subtle my-1"
            }),
            i && q.jsx("button", {
              onClick: te,
              className: "w-9 h-9 flex items-center justify-center bg-accent/20 border border-accent/30 rounded-md text-accent hover:bg-accent/30 transition-colors",
              title: "Focus on Selected Node",
              children: q.jsx(A0, {
                className: "w-4 h-4"
              })
            }),
            re && q.jsx("button", {
              onClick: _,
              className: "w-9 h-9 flex items-center justify-center bg-elevated border border-border-subtle rounded-md text-text-secondary hover:bg-hover hover:text-text-primary transition-colors",
              title: "Clear Selection",
              children: q.jsx(D0, {
                className: "w-4 h-4"
              })
            }),
            q.jsx("div", {
              className: "h-px bg-border-subtle my-1"
            })
          ]
        }),
        q.jsx("div", {
          className: "absolute top-4 right-4 z-20"
        })
      ]
    });
  });
  Xg.displayName = "GraphCanvas";
  let mS = null;
  try {
    mS = (await e0(async () => {
      const { default: e } = await import("./GraphCache-BoqPIAC4.js");
      return {
        default: e
      };
    }, [])).default;
  } catch {
  }
  const vS = () => {
    const { viewMode: e, setViewMode: t, setGraph: n, setFileContents: r, setProgress: i, setProjectName: o, progress: a, runPipeline: s, initializeAgent: l, startEmbeddings: c } = Kp(), h = N.useRef(null), [f, p] = N.useState("dark");
    N.useEffect(() => {
      const k = (b) => {
        var _a2;
        ((_a2 = b.data) == null ? void 0 : _a2.type) === "THEME_CHANGE" && p(b.data.theme === "light" ? "light" : "dark");
      };
      return window.addEventListener("message", k), () => window.removeEventListener("message", k);
    }, []);
    const y = N.useCallback(async (k) => {
      const b = k.name.replace(".zip", "");
      o(b), i({
        phase: "extracting",
        percent: 0,
        message: "Starting...",
        detail: "Preparing to extract files"
      }), t("loading");
      try {
        const I = await s(k, (S) => {
          i(S);
        });
        n(I.graph), r(I.fileContents), t("exploring"), lu() && l(b), c().catch((S) => {
          var _a2;
          (S == null ? void 0 : S.name) === "WebGPUNotAvailableError" || ((_a2 = S == null ? void 0 : S.message) == null ? void 0 : _a2.includes("WebGPU")) ? c("wasm").catch(console.warn) : console.warn("Embeddings auto-start failed:", S);
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
      s,
      c,
      l
    ]);
    return e === "onboarding" ? q.jsx(F0, {
      onFileSelect: y
    }) : e === "loading" && a ? q.jsx(N0, {
      progress: a
    }) : q.jsx("div", {
      className: "flex flex-col h-screen bg-void overflow-hidden",
      children: q.jsx("main", {
        className: "flex-1 flex min-h-0",
        children: q.jsx("div", {
          className: "flex-1 relative min-w-0",
          children: q.jsx(Xg, {
            ref: h,
            background: f
          })
        })
      })
    });
  };
  function yS() {
    return q.jsx(E0, {
      children: q.jsx(vS, {})
    });
  }
  globalThis.Buffer = Np.Buffer;
  hl.createRoot(document.getElementById("root")).render(q.jsx(Pm.StrictMode, {
    children: q.jsx(yS, {})
  }));
})();
