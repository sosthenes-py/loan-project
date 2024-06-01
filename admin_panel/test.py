from rave_python import Rave, RaveExceptions, Misc

rave = Rave("FLWPUBK-f5df39801f412c9cd2526569e6b42d60-X", "FLWSECK-0ea5468775bdaf2e6cc978e8e8184d58-18fb9b21b87vt-X",
            usingEnv=False, production=True)

# mobile payload
payload = {
    "amount": 100,
    "email": "sos.sosthenes1@gmail.com",
    "firstname": "Sosthenes",
    "lastname": "Onyeka",
    "currency": "NGN",
    "tx_ref": "first002",
    "is_permanent": True
}

try:
    res = rave.BankTransfer.charge(payload)
    print(res)

except RaveExceptions.TransactionChargeError as e:
    print(e.err)
    print(e.err["flwRef"])

except RaveExceptions.TransactionVerificationError as e:
    print(e.err["errMsg"])
    print(e.err["txRef"])
