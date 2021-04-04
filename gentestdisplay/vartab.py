# A very simple hierachical data storage

class VarTabException(Exception):
    pass

class VarTab():
    MAX_RECURSION = 10

    def __init__(self, init = {}):
        self.__data = init

    def Load(self, values):
        self.__data = values

    def Reset(self):
        self.Load({})

    def FindValue(self, varname, base=None, write=False):
        varvalue = self.__data if base is None else base

        for piece in varname.split("."):
            # print("FindValue: piece %s varvalue %s" % (piece, varvalue))
            if type(varvalue) is dict:
                if piece in varvalue:
                    varvalue = varvalue[piece]
                elif write:
                    # We are setting values, so create the dictionary entry here
                    varvalue[piece] = {}
                    varvalue = varvalue[piece]
                else:
                    raise VarTabException("Undefined: %s in %s" % (piece, varname))
            elif piece == '':
                raise VarTabException("Ran out of subfields looking for %s" % (varname))
            else:
                raise VarTabException("Trying to get element %s in non-dictionary" % (piece))

        return varvalue

    # Return a value if present, else exception thrown for undefined
    # If no value given, returns entire tree
    def GetValue(self, varname="", base=None, evaluate=True, recursion=0):
        if recursion > self.MAX_RECURSION:
            raise VarTabException("recursion overflow looking for %s" % (varname))

        if varname == "":
            return self.__data if base is None else base

        value = self.FindValue(varname, base=base)

        if evaluate:
            # Process any macros in the varname
            if type(value) is str:
                working = True
                while working:
                    # Look for start of macro
                    start = value.find("${")
                    if start >= 0:
                        # Look for end of macro
                        end = value.find("}", start + 2)
                        if end >= 0:
                            newvalue = self.GetValue(value[start+2:end], recursion=recursion + 1, evaluate=evaluate)
    
                            # String replacement within the text
                            value = value[:start] + str(newvalue) + value[end+1:]
                        else:
                            working = False
                    else:
                        working = False
    
            if type(value) == str:
                # If $evel{xxx} then evaluate expression to get return value
                start = value.find("$eval{")
                if start >= 0:
                    end = value.find("}", start+6)
                    if end >= 0:
                        value = eval(value[start+6:end])

        return value

    def SetValue(self, varname, value, base=None, protect=True):
        try:
            first, last = varname.rsplit('.', maxsplit=1)
            subvar = self.FindValue(first, base=base, write=True)

        except:
            subvar = self.__data if base is None else base
            last = varname

        if protect and last in subvar and (subvar[last].find("$eval{") >= 0 or subvar[last].find("${") >= 0):
            raise VarTabException("Var %s contains evaluated field and not overriden: %s" % (varname, subvar[last]))

        else:
            subvar[last] = value

